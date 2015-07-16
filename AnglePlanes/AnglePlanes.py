from __main__ import vtk, qt, ctk, slicer

import numpy
import SimpleITK as sitk
from math import *



from slicer.ScriptedLoadableModule import *

import os

import sys
import pickle

class AnglePlanes(ScriptedLoadableModule):
    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        parent.title = "Angle Planes"
        parent.categories = ["Shape Analysis"]
        parent.dependencies = []
        parent.contributors = ["Julia Lopinto", "Juan Carlos Prieto"]
        parent.helpText = """
            This Module is used to calculate the angle between two planes by using the normals.
            The user gets the choice to use two planes which are already implemented on Slicer
            or they can define a plane by using landmarks (at least 3 landmarks).
            Plane can also be saved to be reused for other models.
            This is an alpha version of the module.
            It can't be used for the moment.
            """
        
        parent.acknowledgementText = """
            This work was supported by the National
            Institutes of Dental and Craniofacial Research
            and Biomedical Imaging and Bioengineering of
            the National Institutes of Health under Award
            Number R01DE024450.
            """
        
        self.parent = parent

class AnglePlanesWidget(ScriptedLoadableModuleWidget):
    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)
        self.moduleName = "AnglePlanes"
        self.i = 0
        self.logic = AnglePlanesLogic()
        self.planeControlsId = 0
        self.planeControlsDictionary = {}
        self.midPointFiducialDictionaryID = {}
        # self.logic.initializePlane()
        
        self.n_vector = numpy.matrix([[0], [0], [1], [1]])

        self.interactionNode = slicer.mrmlScene.GetNodeByID("vtkMRMLInteractionNodeSingleton")
        #Definition of the 2 planes

        # Collapsible button -- Scene Description
        self.loadCollapsibleButton = ctk.ctkCollapsibleButton()
        self.loadCollapsibleButton.text = "Scene"
        self.layout.addWidget(self.loadCollapsibleButton)

        # Layout within the laplace collapsible button
        self.loadFormLayout = qt.QFormLayout(self.loadCollapsibleButton)

        #--------------------------- List of Models --------------------------#

        treeView = slicer.qMRMLTreeView()
        treeView.setMRMLScene(slicer.app.mrmlScene())
        treeView.setSceneModelType('Displayable')
        treeView.sceneModel().setHorizontalHeaderLabels(["Models"])
        treeView.sortFilterProxyModel().nodeTypes = ['vtkMRMLModelNode']
        header = treeView.header()
        header.setResizeMode(0, qt.QHeaderView.Stretch)
        header.setVisible(True)
        self.loadFormLayout.addWidget(treeView)

        numNodes = slicer.mrmlScene.GetNumberOfNodesByClass("vtkMRMLModelNode")
        for i in range (3,numNodes):
            self.elements = slicer.mrmlScene.GetNthNodeByClass(i,"vtkMRMLModelNode" )
            print self.elements.GetName()

        # Add vertical spacer
        self.layout.addStretch(1)
        #------------------------ Compute Bounding Box ----------------------#
        buttonFrameBox = qt.QFrame(self.parent)
        buttonFrameBox.setLayout(qt.QHBoxLayout())
        self.loadFormLayout.addWidget(buttonFrameBox)

        self.computeBox = qt.QPushButton("Compute Bounding Box around all models")
        buttonFrameBox.layout().addWidget(self.computeBox)
        self.computeBox.connect('clicked()', self.onComputeBox)


        self.CollapsibleButton = ctk.ctkCollapsibleButton()
        self.CollapsibleButton.text = "Manage planes"
        self.layout.addWidget(self.CollapsibleButton)
        self.managePlanesFormLayout = qt.QFormLayout(self.CollapsibleButton)
        self.CollapsibleButton.checked = True

        # Add planes and manage landmark addition to each plane

        addNewPlaneLayout = qt.QHBoxLayout()
        addPlaneLabel = qt.QLabel('Add new plane')
        addPlaneButton = qt.QPushButton(qt.QIcon(":/Icons/MarkupsAddFiducial.png"), " ")
        addPlaneButton.setFixedSize(50,25)
        addPlaneButton.connect('clicked()', self.addNewPlane)
        addPlaneButton.setEnabled(True)
        addNewPlaneLayout.addWidget(addPlaneLabel)
        addNewPlaneLayout.addWidget(addPlaneButton)
        
        self.managePlanesFormLayout.addRow(addNewPlaneLayout)

        #        ----------------- Compute Mid Point -------------   
        self.midPointGroupBox = ctk.ctkCollapsibleButton()
        self.midPointGroupBox.setText('Define middle point between two landmarks') 
        self.midPointGroupBox.collapsed = True
        self.parent.layout().addWidget(self.midPointGroupBox)
        self.landmarkComboBox1MidPoint = qt.QComboBox()
        self.landmarkComboBox2MidPoint = qt.QComboBox()
        landmark1Layout = qt.QFormLayout()
        landmark1Layout.addRow('Landmark A: ', self.landmarkComboBox1MidPoint)
        landmark1Layout.addRow('Landmark B: ', self.landmarkComboBox2MidPoint)

        self.defineMiddlePointButton = qt.QPushButton(' Add middle point ')
        # self.midPointOnSurfaceCheckBox = qt.QCheckBox('On Surface')
        # self.midPointOnSurfaceCheckBox.setChecked(False)
        exportLayout_1 = qt.QFormLayout()
        # exportLayout_1.addRow(self.midPointOnSurfaceCheckBox, self.defineMiddlePointButton)
        exportLayout_1.addRow(self.defineMiddlePointButton)
        self.midPointLayout = qt.QVBoxLayout()
        self.midPointLayout.addLayout(landmark1Layout)
        self.midPointLayout.addLayout(exportLayout_1)
        self.midPointGroupBox.setLayout(self.midPointLayout)

        self.defineMiddlePointButton.connect('clicked()', self.onAddMidPoint)
        # self.landmarkComboBox1MidPoint.connect('currentIndexChanged(int)', self.onUpdateMidPoint)
        # self.landmarkComboBox2MidPoint.connect('currentIndexChanged(int)', self.onUpdateMidPoint)



        # -------- Calculate angles between planes ------------

        self.CollapsibleButtonPlane = ctk.ctkCollapsibleButton()
        self.CollapsibleButtonPlane.text = "Choose planes"
        self.layout.addWidget(self.CollapsibleButtonPlane)
        sampleFormLayoutPlane = qt.QFormLayout(self.CollapsibleButtonPlane)


        self.planeComboBox1 = qt.QComboBox()
        self.planeComboBox1.addItem("red")
        self.planeComboBox1.addItem("yellow")
        self.planeComboBox1.addItem("green")
        sampleFormLayoutPlane.addRow("Select plane 1: ", self.planeComboBox1)


        self.planeComboBox2 = qt.QComboBox()
        self.planeComboBox2.addItem("red")
        self.planeComboBox2.addItem("yellow")
        self.planeComboBox2.addItem("green")
        sampleFormLayoutPlane.addRow("Select plane 2: ", self.planeComboBox2)


        self.CollapsibleButton2 = ctk.ctkCollapsibleButton()
        self.CollapsibleButton2.text = "Results"
        self.layout.addWidget(self.CollapsibleButton2)
        sampleFormLayout2 = qt.QFormLayout(self.CollapsibleButton2)

        self.results = qt.QPushButton("Results")
        self.results.connect('clicked()', self.angleValue)
        sampleFormLayout2.addWidget(self.results)

        label_RL = qt.QLabel("R-L View")
        self.getAngle_RL = qt.QLabel("0")

        label_SI = qt.QLabel("S-I View")
        self.getAngle_SI = qt.QLabel("0")

        label_AP = qt.QLabel("A-P View")
        self.getAngle_AP = qt.QLabel("0")


        self.getAngle_RL_comp = qt.QLabel("0")
        self.getAngle_SI_comp = qt.QLabel("0")
        self.getAngle_AP_comp = qt.QLabel("0")


        tableResult = qt.QTableWidget(3, 3)
        tableResult.setColumnCount(3)
        tableResult.setHorizontalHeaderLabels([' View ', 'Angle', 'Complementary angle'])
        tableResult.setColumnWidth(0, 80)
        tableResult.setColumnWidth(1, 80)
        tableResult.setColumnWidth(2, 180)

        tableResult.setRowCount(1)
        tableResult.setCellWidget(0, 0, label_RL)
        tableResult.setCellWidget(0, 1, self.getAngle_RL)
        tableResult.setCellWidget(0, 2, self.getAngle_RL_comp)

        tableResult.setRowCount(2)
        tableResult.setCellWidget(1, 0, label_SI)
        tableResult.setCellWidget(1, 1, self.getAngle_SI)
        tableResult.setCellWidget(1, 2, self.getAngle_SI_comp)

        tableResult.setRowCount(3)
        tableResult.setCellWidget(2, 0, label_AP)
        tableResult.setCellWidget(2, 1, self.getAngle_AP)
        tableResult.setCellWidget(2, 2, self.getAngle_AP_comp)


        # Add vertical spacer
        self.layout.addStretch(1)

        sampleFormLayout2.addWidget(tableResult)

        self.CollapsibleButton3 = ctk.ctkCollapsibleButton()
        self.CollapsibleButton3.text = "Save"
        self.layout.addWidget(self.CollapsibleButton3)
        sampleFormLayout3 = qt.QFormLayout(self.CollapsibleButton3)
        self.CollapsibleButton3.checked = False

        buttonFrame = qt.QFrame(self.parent)
        buttonFrame.setLayout(qt.QVBoxLayout())
        sampleFormLayout3.addWidget(buttonFrame)

        #-------------------------------- PLANES --------------------------------#
        save_plane = qt.QLabel("Save the planes you create as a txt file.")
        buttonFrame.layout().addWidget(save_plane)
        save = qt.QPushButton("Save plane")
        buttonFrame.layout().addWidget(save)

        # load_plane = qt.QLabel("Load the file with the plane you saved.")
        # buttonFrame.layout().addWidget(load_plane)
        read = qt.QPushButton("Load plane")
        buttonFrame.layout().addWidget(read)

        #-------------------------------- CONNECTIONS --------------------------------#
        self.planeComboBox1.connect('currentIndexChanged(QString)', self.valueComboBox)
        self.planeComboBox2.connect('currentIndexChanged(QString)', self.valueComboBox)

        save.connect('clicked(bool)', self.onSavePlanes)
        read.connect('clicked(bool)', self.onReadPlanes)
                                                                                                                
        slicer.mrmlScene.AddObserver(slicer.mrmlScene.EndCloseEvent, self.onCloseScene)

    def addNewPlane(self, keyLoad = -1):
        if keyLoad != -1:
            self.planeControlsId = keyLoad
        else:
            self.planeControlsId += 1

        planeControls = AnglePlanesWidgetPlaneControl(self, self.planeControlsId)
        self.managePlanesFormLayout.addRow(planeControls)

        key = "Plane " + str(self.planeControlsId)        
        self.planeControlsDictionary[key] = planeControls

        self.planeComboBox1.addItem(key)
        self.planeComboBox2.addItem(key)
    
    def onComputeBox(self):
        numNodes = slicer.mrmlScene.GetNumberOfNodesByClass("vtkMRMLModelNode")
        bound = [sys.maxsize, -sys.maxsize, sys.maxsize, -sys.maxsize, sys.maxsize, -sys.maxsize]
        for i in range (3,numNodes):
            self.elements = slicer.mrmlScene.GetNthNodeByClass(i,"vtkMRMLModelNode" )
            node = slicer.util.getNode(self.elements.GetName())
            polydata = node.GetPolyData()
            tempbound = polydata.GetBounds()
            bound[0] = min(bound[0], tempbound[0])
            bound[2] = min(bound[2], tempbound[2])
            bound[4] = min(bound[4], tempbound[4])

            bound[1] = max(bound[1], tempbound[1])
            bound[3] = max(bound[3], tempbound[3])
            bound[5] = max(bound[5], tempbound[5])

        #--------------------------- Box around the model --------------------------#
        
        print "bound", bound
        
        dimX = bound[1]-bound[0]
        dimY = bound[3]-bound[2]
        dimZ = bound[5]-bound[4]
        
        print "dimension X :", dimX
        print "dimension Y :", dimY
        print "dimension Z :", dimZ
        
        dimX = dimX + 10
        dimY = dimY + 20
        dimZ = dimZ + 20

        red = slicer.util.getNode('vtkMRMLSliceNodeRed')
        red.SetDimensions(dimX, dimY, dimZ)
        red.SetOrigin(bound[0], bound[1], bound[2])
        
        # center = [0, 0, 0]
        # center[0] = (bound[1]+bound[0])/2
        # center[1] = (bound[3]+bound[2])/2
        # center[2] = (bound[5]+bound[4])/2

        
        # # Creation of an Image
        # self.image = sitk.Image(int(dimX), int(dimY), int(dimZ), sitk.sitkInt16)
        
        # dir = (-1.0, 0.0, 0.0, 0.0, -1.0, 0.0, 0.0, 0.0, 1.0)
        # self.image.SetDirection(dir)
        
        # spacing = (1,1,1)
        # self.image.SetSpacing(spacing)
        
        # tab = [-center[0]+dimX/2,-center[1]+dimY/2,center[2]-dimZ/2]
        # print tab
        # self.image.SetOrigin(tab)
        
        
        # writer = sitk.ImageFileWriter()
        # tempPath = slicer.app.temporaryPath
        # filename = "Box.nrrd"
        # filenameFull=os.path.join(tempPath,filename)
        # print filenameFull
        # writer.SetFileName(str(filenameFull))
        # writer.Execute(self.image)
        
        
        # slicer.util.loadVolume(filenameFull)
        
        # #------------------------ Slice Intersection Visibility ----------------------#
        # numDisplayNode = slicer.mrmlScene.GetNumberOfNodesByClass("vtkMRMLModelDisplayNode")
        # for i in range (3,numDisplayNode):
        #     self.slice = slicer.mrmlScene.GetNthNodeByClass(i,"vtkMRMLModelDisplayNode" )
        #     self.slice.SetSliceIntersectionVisibility(1)
        
    def onAddMidPoint(self):
        
        f1 = self.landmarkComboBox1MidPoint.currentText
        f2 = self.landmarkComboBox2MidPoint.currentText

        p1 = f1[0:f1.find("-")]
        print p1

        fidlist1 = slicer.mrmlScene.GetNodesByClassByName('vtkMRMLMarkupsFiducialNode', p1).GetItemAsObject(0)
        index1 = fidlist1.GetMarkupIndexByID(self.midPointFiducialDictionaryID[f1])
        coord1 = numpy.zeros(3)
        fidlist1.GetNthFiducialPosition(index1, coord1)

        p2 = f2[0:f2.find("-")]
        print p2

        fidlist2 = slicer.mrmlScene.GetNodesByClassByName('vtkMRMLMarkupsFiducialNode', p2).GetItemAsObject(0)
        index2 = fidlist2.GetMarkupIndexByID(self.midPointFiducialDictionaryID[f2])
        coord2 = numpy.zeros(3)
        fidlist2.GetNthFiducialPosition(index2, coord2)

        coord = coord1 + coord2
        coord /= 2

        fidlist1.AddFiducial(coord[0], coord[1], coord[2])

        if p1 != p2:
            fidlist2.AddFiducial(coord[0], coord[1], coord[2])
            fidlist2.SetNthFiducialVisibility(fidlist2.GetNumberOfFiducials() - 1, False)
        

    def onFiducialAddedMidPoint(self, obj, event):
        fidlist = obj

        label = fidlist.GetNthFiducialLabel(fidlist.GetNumberOfFiducials() - 1)

        self.midPointFiducialDictionaryID[label] = fidlist.GetNthMarkupID(fidlist.GetNumberOfFiducials() - 1)

        self.landmarkComboBox1MidPoint.addItem(label)
        self.landmarkComboBox2MidPoint.addItem(label)

    def onFiducialRemovedMidPoint(self, obj, event):
        fidlist = obj

        print obj
        
        for i in range(1, self.landmarkComboBox1MidPoint.count):
            print i
            label = self.landmarkComboBox1MidPoint.itemText(i)
            found = self.fiducialInListMidPoint(label, fidlist)
            if not found:
                del self.midPointFiducialDictionaryID[label]
                self.landmarkComboBox1MidPoint.removeItem(i)
                self.landmarkComboBox2MidPoint.removeItem(i)
                break

    def fiducialInListMidPoint(self, name, fidlist):
        for i in range(0, fidlist.GetNumberOfFiducials()):
            if name == fidlist.GetNthFiducialLabel(i) :
                return True
        return False

    
    def onCloseScene(self, obj, event):
        keys = self.planeControlsDictionary.keys()
        for i in range(0, len(keys)):
            self.planeControlsDictionary[keys[i]].remove()
            del self.planeControlsDictionary[keys[i]]
        
        globals()[self.moduleName] = slicer.util.reloadScriptedModule(self.moduleName)
    
    def angleValue(self):
        self.valueComboBox()
        
        self.getAngle_RL.setText(self.logic.angle_degre_RL)
        self.getAngle_RL_comp.setText(self.logic.angle_degre_RL_comp)
        
        self.getAngle_SI.setText(self.logic.angle_degre_SI)
        self.getAngle_SI_comp.setText(self.logic.angle_degre_SI_comp)
        
        self.getAngle_AP.setText(self.logic.angle_degre_AP)
        self.getAngle_AP_comp.setText(self.logic.angle_degre_AP_comp)
    
    def valueComboBox(self):
        
        colorPlane1 = self.planeComboBox1.currentText
        colorPlane2 = self.planeComboBox2.currentText
        
        print colorPlane1
        print colorPlane2
        
        redslice = slicer.mrmlScene.GetNodeByID('vtkMRMLSliceNodeRed')
        redslice.SetWidgetVisible(False)
        
        yellowslice = slicer.mrmlScene.GetNodeByID('vtkMRMLSliceNodeYellow')
        yellowslice.SetWidgetVisible(False)
        
        greenslice = slicer.mrmlScene.GetNodeByID('vtkMRMLSliceNodeGreen')
        greenslice.SetWidgetVisible(False)
        
        self.defineAngle(colorPlane1,colorPlane2)
    
    def modify(self, obj, event):
        self.defineAngle(self.planeComboBox1.currentText, self.planeComboBox2.currentText)

    def defineAngle(self, colorPlane1, colorPlane2):
        print "DEFINE ANGLE"
        print colorPlane1
        if colorPlane1 in self.logic.ColorNodeCorrespondence:
            slice1 = slicer.util.getNode(self.logic.ColorNodeCorrespondence[colorPlane1])
            self.logic.getMatrix(slice1)
            slice1.SetWidgetVisible(True)
            matrix1 = self.logic.getMatrix(slice1)
            normal1 = self.logic.defineNormal(matrix1)
        else:
            normal1 = self.planeControlsDictionary[colorPlane1].logic.N
        
        print colorPlane2
        if colorPlane2 in self.logic.ColorNodeCorrespondence:
            slice2 = slicer.util.getNode(self.logic.ColorNodeCorrespondence[colorPlane2])
            self.logic.getMatrix(slice2)
            slice2.SetWidgetVisible(True)
            matrix2 = self.logic.getMatrix(slice2)
            normal2 = self.logic.defineNormal(matrix2)
        else:
            normal2 = self.planeControlsDictionary[colorPlane2].logic.N

        self.logic.getAngle(normal1, normal2)

    def onSavePlanes(self):
        self.savePlanes()

    def savePlanes(self, filename = None):
        tempDictionary = {}

        sliceRed = slicer.util.getNode(self.logic.ColorNodeCorrespondence['red'])
        tempDictionary["red"] = self.logic.getMatrix(sliceRed).tolist()
        
        sliceYellow = slicer.util.getNode(self.logic.ColorNodeCorrespondence['yellow'])
        tempDictionary["yellow"] = self.logic.getMatrix(sliceYellow).tolist()
        
        sliceGreen = slicer.util.getNode(self.logic.ColorNodeCorrespondence['green'])
        tempDictionary["green"] = self.logic.getMatrix(sliceGreen).tolist()
        
        tempDictionary["customPlanes"] = {}

        for key, plane in self.planeControlsDictionary.items():
            tempDictionary["customPlanes"][plane.id] = plane.getFiducials()
        print filename
        if filename is None:
            filename = qt.QFileDialog.getSaveFileName(parent=self, caption='Save file')

        if filename != "":
            fileObj = open(filename, "wb")
            pickle.dump(tempDictionary, fileObj)
            fileObj.close()

    def onReadPlanes(self):
        self.readPlanes()

    def readPlanes(self, filename=None):

        if filename is None:
            filename = qt.QFileDialog.getOpenFileName(parent=self,caption='Open file')
        
        if filename != "":
            fileObj = open(filename, "rb")
            tempDictionary = pickle.load( fileObj )

            node = slicer.mrmlScene.GetNodeByID('vtkMRMLSliceNodeRed')
            matList = tempDictionary["red"]
            matNode = node.GetSliceToRAS()

            for col in range(0, len(matList)):
                for row in range(0, len(matList[col])):
                    matNode.SetElement(col, row, matList[col][row])

            node = slicer.mrmlScene.GetNodeByID('vtkMRMLSliceNodeYellow')
            matList = tempDictionary["yellow"]
            matNode = node.GetSliceToRAS()

            for col in range(0, len(matList)):
                for row in range(0, len(matList[col])):
                    matNode.SetElement(col, row, matList[col][row])

            node = slicer.mrmlScene.GetNodeByID('vtkMRMLSliceNodeGreen')
            matList = tempDictionary["green"]
            matNode = node.GetSliceToRAS()

            for col in range(0, len(matList)):
                for row in range(0, len(matList[col])):
                    matNode.SetElement(col, row, matList[col][row])


            customPlanes = tempDictionary["customPlanes"]

            for key, fidList in customPlanes.items():
                self.addNewPlane(key)
                tempkey = "Plane " + str(self.planeControlsId)
                currentFidList = self.planeControlsDictionary[tempkey].logic.getFiducialList()
                for i in range(0, len(fidList)):
                    f = fidList[i]
                    currentFidList.AddFiducial(f[0], f[1], f[2])

            fileObj.close()

# This widget controls each of the planes that are added to the interface. 
# The widget contains its own logic, i.e. an object of AnglePlanesLogic. 
# Each plane contains a separate fiducial list. The planes are named P1, P2, ..., PN. The landmarks are named
# P1-1, P1-2, P1-N. 
class AnglePlanesWidgetPlaneControl(qt.QFrame):
    def __init__(self, anglePlanes, id):
        qt.QFrame.__init__(self)
        self.id = id

        self.setLayout(qt.QFormLayout())

        landmarkLayout = qt.QHBoxLayout()
        

        planeLabel = qt.QLabel('Plane ' + str(id) + ":")
        landmarkLayout.addWidget(planeLabel)

        self.logic = AnglePlanesLogic(id)

        label1 = qt.QLabel(' L1:')
        self.landmark1ComboBox = qt.QComboBox()
        landmark1ComboBox = self.landmark1ComboBox
        landmark1ComboBox.addItem("Select")
        landmark1ComboBox.connect('currentIndexChanged(QString)', self.placePlaneClicked)

        landmarkLayout.addWidget(label1)
        landmarkLayout.addWidget(landmark1ComboBox)

        label2 = qt.QLabel(' L2:')
        self.landmark2ComboBox = qt.QComboBox()
        landmark2ComboBox = self.landmark2ComboBox
        landmark2ComboBox.addItem("Select")
        landmark2ComboBox.connect('currentIndexChanged(QString)', self.placePlaneClicked)

        landmarkLayout.addWidget(label2)
        landmarkLayout.addWidget(landmark2ComboBox)

        label3 = qt.QLabel(' L3:')
        self.landmark3ComboBox = qt.QComboBox()
        landmark3ComboBox = self.landmark3ComboBox
        landmark3ComboBox.addItem("Select")
        landmark3ComboBox.connect('currentIndexChanged(QString)', self.placePlaneClicked)

        landmarkLayout.addWidget(label3)
        landmarkLayout.addWidget(landmark3ComboBox)

        addFiducialLabel = qt.QLabel('Add')
        addFiducialButton = qt.QPushButton(qt.QIcon(":/Icons/MarkupsAddFiducial.png"), " ")
        addFiducialButton.setFixedSize(50,25)
        addFiducialButton.connect('clicked()', self.addLandMarkClicked)
        addFiducialButton.setEnabled(True)
        landmarkLayout.addWidget(addFiducialLabel)
        landmarkLayout.addWidget(addFiducialButton)

        #fiducial list for the plane

        fidNode = self.logic.getFiducialList()
        for i in range(0, fidNode.GetNumberOfFiducials()):
            label = fidNode.GetNthFiducialLabel(i)
            landmark1ComboBox.addItem(label)
            landmark2ComboBox.addItem(label)
            landmark3ComboBox.addItem(label)

            anglePlanes.landmarkComboBox1MidPoint.addItem(label)
            anglePlanes.landmarkComboBox2MidPoint.addItem(label)
            anglePlanes.midPointFiducialDictionaryID[label] = fidNode.GetNthMarkupID(i)

        fidNode.AddObserver(fidNode.MarkupAddedEvent, self.onFiducialAdded)
        fidNode.AddObserver(fidNode.MarkupRemovedEvent, self.onFiducialRemoved)
        fidNode.AddObserver(fidNode.PointModifiedEvent, self.onPointModifiedEvent)


        # This observers are in AnglePlaneWidgets, they listen to any fiducial being added
        # 
        fidNode.AddObserver(fidNode.MarkupAddedEvent, anglePlanes.onFiducialAddedMidPoint)
        fidNode.AddObserver(fidNode.MarkupRemovedEvent, anglePlanes.onFiducialRemovedMidPoint)


        self.layout().addRow(landmarkLayout)

        self.slider = ctk.ctkSliderWidget()
        slider = self.slider
        slider.singleStep = 0.1
        slider.minimum = 0.1
        slider.maximum = 10
        slider.value = 1.0
        slider.toolTip = "Set the size of your plane."

        self.slideOpacity = ctk.ctkSliderWidget()
        slideOpacity = self.slideOpacity
        slideOpacity.singleStep = 0.1
        slideOpacity.minimum = 0.1
        slideOpacity.maximum = 1
        slideOpacity.value = 1.0
        slideOpacity.toolTip = "Set the opacity of your plane."

        slider.connect('valueChanged(double)', self.placePlaneClicked)
        slideOpacity.connect('valueChanged(double)', self.placePlaneClicked)

        landmarkSliderLayout = qt.QHBoxLayout()
        
        label = qt.QLabel(' Size:')
        label2 = qt.QLabel(' Opacity:')

        landmarkSliderLayout.addWidget(label)
        landmarkSliderLayout.addWidget(self.slider)
        landmarkSliderLayout.addWidget(label2)
        landmarkSliderLayout.addWidget(self.slideOpacity)

        self.layout().addRow(landmarkSliderLayout)

    def remove(self):
        self.logic.remove()
        
    def onFiducialRemoved(self, obj, event):
        fidlist = obj
        
        for i in range(1, self.landmark1ComboBox.count):
            print i
            found = self.fiducialInList(self.landmark1ComboBox.itemText(i), fidlist)
            if not found:
                self.landmark1ComboBox.removeItem(i)
                self.landmark2ComboBox.removeItem(i)
                self.landmark3ComboBox.removeItem(i)
                break

    def getFiducials(self):
        
        fidNode = self.logic.getFiducialList()

        listCoord = list()

        coord = numpy.zeros(3)
        fidNode.GetNthFiducialPosition(int(self.landmark1ComboBox.currentIndex)-1, coord)
        listCoord.append(coord)

        fidNode.GetNthFiducialPosition(int(self.landmark2ComboBox.currentIndex)-1, coord)
        listCoord.append(coord)

        fidNode.GetNthFiducialPosition(int(self.landmark3ComboBox.currentIndex)-1, coord)
        listCoord.append(coord)
        
        return listCoord

    def placePlaneClicked(self):
        self.logic.planeLandmarks(self.landmark1ComboBox.currentIndex, self.landmark2ComboBox.currentIndex, self.landmark3ComboBox.currentIndex, self.slider.value, self.slideOpacity.value)

    def fiducialInList(self, name, fidlist):
        for i in range(0, fidlist.GetNumberOfFiducials()):
            if name == fidlist.GetNthFiducialLabel(i) :
                return True
        return False

    def onPointModifiedEvent(self, obj, event):
        self.logic.planeLandmarks(self.landmark1ComboBox.currentIndex, self.landmark2ComboBox.currentIndex, self.landmark3ComboBox.currentIndex, self.slider.value, self.slideOpacity.value)

    def addLandMarkClicked(self):
        print "Add landmarks"
        # # Place landmarks in the 3D scene
        fidlist = self.logic.getFiducialList()
        slicer.mrmlScene.AddNode(fidlist)
        interactionNode = slicer.mrmlScene.GetNodeByID("vtkMRMLInteractionNodeSingleton")
        interactionNode.SetCurrentInteractionMode(1)

    def onFiducialAdded(self, obj, event):
        fidlist = obj

        label = fidlist.GetNthFiducialLabel(fidlist.GetNumberOfFiducials() - 1)
        
        self.landmark1ComboBox.addItem(label)
        self.landmark2ComboBox.addItem(label)
        self.landmark3ComboBox.addItem(label)
    

class AnglePlanesLogic(ScriptedLoadableModuleLogic):
    def __init__(self, id = -1):
        self.ColorNodeCorrespondence = {'red': 'vtkMRMLSliceNodeRed',
            'yellow': 'vtkMRMLSliceNodeYellow',
            'green': 'vtkMRMLSliceNodeGreen'}
        self.id = id
        self.initialize()

    def initialize(self):
        self.layoutManager=slicer.app.layoutManager()
        self.threeDWidget=self.layoutManager.threeDWidget(0)
        self.threeDView=self.threeDWidget.threeDView()
        self.renderWindow=self.threeDView.renderWindow()
        self.renderers=self.renderWindow.GetRenderers()
        self.renderer=self.renderers.GetFirstRenderer()
        
        self.polydata = vtk.vtkPolyData()
        self.points = vtk.vtkPoints()
        self.planeSource = vtk.vtkPlaneSource()
        self.mapper = vtk.vtkPolyDataMapper()
        self.actor = vtk.vtkActor()
        self.renderer.AddViewProp(self.actor)
        self.renderWindow.AddRenderer(self.renderer)

    def remove(self):
        self.renderer.RemoveViewProp(self.actor)
        self.renderer.Render()

    def getFiducialList(self):
        
        P = self.getFiducialListName()
        nodes = slicer.mrmlScene.GetNodesByClassByName('vtkMRMLMarkupsFiducialNode', P)

        if nodes.GetNumberOfItems() == 0:
            # The list does not exist so we create it

            fidNode = slicer.vtkMRMLMarkupsFiducialNode()
            fidNode.SetName(P)
            slicer.mrmlScene.AddNode(fidNode)
            
        else:
            #The list exists but the observers must be updated
            fidNode = nodes.GetItemAsObject(0)

        return fidNode

    def getFiducialListName(self) :
        return "P" + str(self.id)
    
    def getMatrix(self, slice):
        self.mat = slice.GetSliceToRAS()
        print self.mat
        #---------------------- RED SLICE -----------------------#
        # Matrix with the elements of SliceToRAS
        m = numpy.matrix([[self.mat.GetElement(0,0), self.mat.GetElement(0,1), self.mat.GetElement(0,2), self.mat.GetElement(0,3)],
                          [self.mat.GetElement(1,0), self.mat.GetElement(1,1), self.mat.GetElement(1,2), self.mat.GetElement(1,3)],
                          [self.mat.GetElement(2,0), self.mat.GetElement(2,1), self.mat.GetElement(2,2), self.mat.GetElement(2,3)],
                          [self.mat.GetElement(3,0), self.mat.GetElement(3,1), self.mat.GetElement(3,2), self.mat.GetElement(3,3)]])
        return m
    
    def defineNormal(self, matrix):
        
        # Normal vector to the Red slice:
        n_vector = numpy.matrix([[0],[0],[1],[1]])
        
        # point on the Red slice:
        A = numpy.matrix([[0], [0], [0], [1]])
        
        normalVector = matrix * n_vector
        print "n : \n", normalVector
        A = matrix * A
        
        
        normalVector1 = normalVector
        
        
        normalVector1[0] = normalVector[0] - A[0]
        normalVector1[1] = normalVector[1] - A[1]
        normalVector1[2] = normalVector[2] - A[2]
        print normalVector1
        
        return normalVector1
    
    def getAngle(self, normalVect1, normalVect2):
        
        norm1 = sqrt(normalVect1[0]*normalVect1[0]+normalVect1[1]*normalVect1[1]+normalVect1[2]*normalVect1[2])
        print "norme 1: \n", norm1
        norm2 =sqrt(normalVect2[0]*normalVect2[0]+normalVect2[1]*normalVect2[1]+normalVect2[2]*normalVect2[2])
        print "norme 2: \n", norm2
        
        
        scalar_product = (normalVect1[0]*normalVect2[0]+normalVect1[1]*normalVect2[1]+normalVect1[2]*normalVect2[2])
        print "scalar product : \n", scalar_product
        
        angle = acos(scalar_product/(norm1*norm2))
        print "radian angle : ", angle
        
        angle_degree = angle*180/pi
        print "Angle in degree", angle_degree
        
        
        norm1_RL = sqrt(normalVect1[1]*normalVect1[1]+normalVect1[2]*normalVect1[2])
        print "norme RL: \n", norm1_RL
        norm2_RL =sqrt(normalVect2[1]*normalVect2[1]+normalVect2[2]*normalVect2[2])
        print "norme RL: \n", norm2_RL
        
        if (norm1_RL ==0 or norm1_RL ==0):
            self.angle_degre_RL = 0
            self.angle_degre_RL_comp = 0
        else:
            scalar_product_RL = (normalVect1[1]*normalVect2[1]+normalVect1[2]*normalVect2[2])
            print "scalar product : \n", scalar_product_RL
            
            angleRL = acos(scalar_product_RL/(norm1_RL*norm2_RL))
            print "radian angle : ", angleRL
            
            self.angle_degre_RL = angleRL*180/pi
            self.angle_degre_RL = round(self.angle_degre_RL,2)
            print self.angle_degre_RL
            self.angle_degre_RL_comp = 180-self.angle_degre_RL
        
        
        norm1_SI = sqrt(normalVect1[0]*normalVect1[0]+normalVect1[1]*normalVect1[1])
        print "norme1_SI : \n", norm1_SI
        norm2_SI =sqrt(normalVect2[0]*normalVect2[0]+normalVect2[1]*normalVect2[1])
        print "norme2_SI : \n", norm2_SI
        
        if (norm1_SI ==0 or norm2_SI ==0):
            self.angle_degre_SI = 0
            self.angle_degre_SI_comp = 0
        else:
            scalar_product_SI = (normalVect1[0]*normalVect2[0]+normalVect1[1]*normalVect2[1])
            print "scalar product_SI : \n", scalar_product_SI
            
            angleSI = acos(scalar_product_SI/(norm1_SI*norm2_SI))
            print "radian angle : ", angleSI
            
            self.angle_degre_SI = angleSI*180/pi
            self.angle_degre_SI = round(self.angle_degre_SI,2)
            print self.angle_degre_SI
            self.angle_degre_SI_comp = 180-self.angle_degre_SI
            print self.angle_degre_SI_comp
        
        norm1_AP = sqrt(normalVect1[0]*normalVect1[0]+normalVect1[2]*normalVect1[2])
        print "norme1_SI : \n", norm1_AP
        norm2_AP =sqrt(normalVect2[0]*normalVect2[0]+normalVect2[2]*normalVect2[2])
        print "norme2_SI : \n", norm2_AP
        
        if (norm1_AP ==0 or norm2_AP ==0):
            self.angle_degre_AP = 0
            self.angle_degre_AP_comp = 0
        else:
            scalar_product_AP = (normalVect1[0]*normalVect2[0]+normalVect1[2]*normalVect2[2])
            print "scalar product_SI : \n", scalar_product_AP
            
            print "VALUE :", scalar_product_AP/(norm1_AP*norm2_AP)
            
            angleAP = acos(scalar_product_AP/(norm1_AP*norm2_AP))
            
            print "radian angle : ", angleAP
            
            self.angle_degre_AP = angleAP*180/pi
            self.angle_degre_AP = round(self.angle_degre_AP,2)
            print self.angle_degre_AP
            self.angle_degre_AP_comp = 180-self.angle_degre_AP
    
    def normalLandmarks(self, GA, GB):
        Vn = numpy.matrix([[0],[0],[0]])
        Vn[0] = GA[1]*GB[2] - GA[2]*GB[1]
        Vn[1] = GA[2]*GB[0] - GA[0]*GB[2]
        Vn[2] = GA[0]*GB[1] - GA[1]*GB[0]
        
        print "Vn = ",Vn
        
        norm_Vn = sqrt(Vn[0]*Vn[0]+Vn[1]*Vn[1]+Vn[2]*Vn[2])
        
        Normal = Vn/norm_Vn
        
        print "N = ",Normal
        
        return Normal
    
    def defineNormal(self, matrix):
        
        # Normal vector to the Red slice:
        n_vector = numpy.matrix([[0],[0],[1],[1]])
        
        # point on the Red slice:
        A = numpy.matrix([[0], [0], [0], [1]])
        
        normalVector = matrix * n_vector
        print "n : \n", normalVector
        A = matrix * A
        
        normalVector1 = normalVector
        
        normalVector1[0] = normalVector[0] - A[0]
        normalVector1[1] = normalVector[1] - A[1]
        normalVector1[2] = normalVector[2] - A[2]
        print normalVector1
        
        return normalVector1
    
    def planeLandmarks(self, Landmark1Value, Landmark2Value, Landmark3Value, slider, sliderOpacity):
        # Limit the number of 3 landmarks to define a plane
        # Keep the coordinates of the landmarks
        fidNode = self.getFiducialList()

        r1 = 0
        a1 = 0
        s1 = 0
        coord = numpy.zeros(3)
        
        if Landmark1Value != 0:
            fidNode.GetNthFiducialPosition(int(Landmark1Value)-1, coord)
            r1 = coord[0]
            a1 = coord[1]
            s1 = coord[2]
        
        
        # Limit the number of 3 landmarks to define a plane
        # Keep the coordinates of the landmarks
        r2 = 0
        a2 = 0
        s2 = 0
        if Landmark2Value != 0:
            fidNode.GetNthFiducialPosition(int(Landmark2Value)-1, coord)
            r2 = coord[0]
            a2 = coord[1]
            s2 = coord[2]
        
        # Limit the number of 3 landmarks to define a plane
        # Keep the coordinates of the landmarks
        r3 = 0
        a3 = 0
        s3 = 0
        if Landmark3Value != 0:
            fidNode.GetNthFiducialPosition(int(Landmark3Value)-1, coord)
            r3 = coord[0]
            a3 = coord[1]
            s3 = coord[2]
        
        
        points = self.points
        if points.GetNumberOfPoints() == 0:
            points.InsertNextPoint(r1,a1,s1)
            points.InsertNextPoint(r2,a2,s2)
            points.InsertNextPoint(r3,a3,s3)
        else:
            points.SetPoint(0, r1,a1,s1)
            points.SetPoint(1, r2,a2,s2)
            points.SetPoint(2, r3,a3,s3)

            
        polydata = self.polydata
        polydata.SetPoints(points)

        centerOfMass = vtk.vtkCenterOfMass()
        centerOfMass.SetInputData(polydata)
        centerOfMass.SetUseScalarsAsWeights(False)
        centerOfMass.Update()
        
        G = centerOfMass.GetCenter()
        
        print "Center of mass = ",G
        
        A = (r1,a1,s1)
        B = (r2,a2,s2)
        C = (r3,a3,s3)

        # Vector GA
        GA = numpy.matrix([[0],[0],[0]])
        GA[0] = A[0]-G[0]
        GA[1] = A[1]-G[1]
        GA[2] = A[2]-G[2]
        
        print "GA = ", GA
        
        # Vector BG
        GB = numpy.matrix([[0],[0],[0]])
        GB[0] = B[0]-G[0]
        GB[1] = B[1]-G[1]
        GB[2] = B[2]-G[2]
        
        print "GB = ", GB
        
        # Vector CG
        GC = numpy.matrix([[0],[0],[0]])
        GC[0] = C[0]-G[0]
        GC[1] = C[1]-G[1]
        GC[2] = C[2]-G[2]
        
        print "GC = ", GC
        
        self.N = self.normalLandmarks(GA,GB)
        
        D = numpy.matrix([[0],[0],[0]])
        E = numpy.matrix([[0],[0],[0]])
        F = numpy.matrix([[0],[0],[0]])
        
        
        D[0] = slider*GA[0] + G[0]
        D[1] = slider*GA[1] + G[1]
        D[2] = slider*GA[2] + G[2]
        
        print "Slider value : ", slider
        
        print "D = ",D
        
        E[0] = slider*GB[0] + G[0]
        E[1] = slider*GB[1] + G[1]
        E[2] = slider*GB[2] + G[2]
        
        print "E = ",E
        
        F[0] = slider*GC[0] + G[0]
        F[1] = slider*GC[1] + G[1]
        F[2] = slider*GC[2] + G[2]
        
        print "F = ",F

        planeSource = self.planeSource
        planeSource.SetNormal(self.N[0],self.N[1],self.N[2])
        
        planeSource.SetOrigin(D[0],D[1],D[2])
        planeSource.SetPoint1(E[0],E[1],E[2])
        planeSource.SetPoint2(F[0],F[1],F[2])
        
        planeSource.Update()
        
        plane = planeSource.GetOutput()
        
        mapper = self.mapper
        mapper.SetInputData(plane)
        mapper.Update()
        
        self.actor.SetMapper(mapper)
        self.actor.GetProperty().SetColor(0, 0.4, 0.8)
        self.actor.GetProperty().SetOpacity(sliderOpacity)
        
        self.renderer.Render()
        self.renderWindow.Render()


class AnglePlanesTest(ScriptedLoadableModuleTest):
    def setUp(self):
        # reset the state - clear scene
        slicer.mrmlScene.Clear(0)
    
    def runTest(self):
        # run all tests needed
        self.setUp()
        self.test_AnglePlanes()
    
    def test_AnglePlanes(self):

        self.delayDisplay('Starting the test')

        self.delayDisplay('Adding planes')
        widget = AnglePlanesWidget()

        widget.addNewPlane()
        widget.addNewPlane()

        self.delayDisplay('Adding fiducials')
        fidlist1 = slicer.mrmlScene.GetNodesByClassByName('vtkMRMLMarkupsFiducialNode', "P1").GetItemAsObject(0)

        fidlist1.AddFiducial(10,10,10)
        fidlist1.AddFiducial(20,20,20)
        fidlist1.AddFiducial(10,20,30)

        fidlist2 = slicer.mrmlScene.GetNodesByClassByName('vtkMRMLMarkupsFiducialNode', "P2").GetItemAsObject(0)

        fidlist2.AddFiducial(50,50,50)
        fidlist2.AddFiducial(40,20,80)
        fidlist2.AddFiducial(10,40,20)
        

        self.delayDisplay('Saving planes')
        widget.savePlanes("test.p")

        self.delayDisplay('Loading planes')
        widget.readPlanes("test.p")

        self.delayDisplay('Selecting fiducials')
        widget.planeControlsDictionary["Plane 1"].landmark1ComboBox.setCurrentIndex(1)
        widget.planeControlsDictionary["Plane 1"].landmark2ComboBox.setCurrentIndex(2)
        widget.planeControlsDictionary["Plane 1"].landmark3ComboBox.setCurrentIndex(3)

        widget.planeControlsDictionary["Plane 2"].landmark1ComboBox.setCurrentIndex(1)
        widget.planeControlsDictionary["Plane 2"].landmark2ComboBox.setCurrentIndex(2)
        widget.planeControlsDictionary["Plane 2"].landmark3ComboBox.setCurrentIndex(3)

        self.delayDisplay('Selecting planes')
        widget.planeComboBox1.setCurrentIndex(5)
        widget.planeComboBox2.setCurrentIndex(6)

        self.delayDisplay('Calculating angle')
        widget.angleValue()

        test = widget.logic.angle_degre_RL != 59.06 or widget.logic.angle_degre_RL_comp != 120.94 or widget.logic.angle_degre_SI != 12.53 or widget.logic.angle_degre_SI_comp != 167.47 or widget.logic.angle_degre_AP != 82.56 or widget.logic.angle_degre_AP_comp != 97.44

        self.delayDisplay('Testing angles')
        if test:

            print "", "Angle", "Complementary"
            print "R-L-View", self.logic.angle_degre_RL, self.logic.angle_degre_RL_comp
            print "S-I-View", self.logic.angle_degre_SI, self.logic.angle_degre_SI_comp
            print "A-P-View", self.logic.angle_degre_AP, self.logic.angle_degre_AP_comp
            self.delayDisplay('Test Failure!')

        else:
            self.delayDisplay('Test passed!')
        
        widget.parent.close()

