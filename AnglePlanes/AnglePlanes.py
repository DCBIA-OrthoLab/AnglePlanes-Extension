import os
from __main__ import vtk, qt, ctk, slicer
import logging
import numpy
import time
from math import *

from slicer.ScriptedLoadableModule import *

import pickle
import json

from slicer.util import VTKObservationMixin


class ModelAddedClass(VTKObservationMixin):
    def __init__(self, anglePlanes):
        VTKObservationMixin.__init__(self)
        self.addObserver(slicer.mrmlScene, slicer.vtkMRMLScene.NodeAddedEvent, self.nodeAddedCallback)
        self.addObserver(slicer.mrmlScene, slicer.vtkMRMLScene.NodeRemovedEvent, self.nodeRemovedCallback)
        self.anglePlanes = anglePlanes

    @vtk.calldata_type(vtk.VTK_OBJECT)
    def nodeAddedCallback(self, caller, eventId, callData):
        if isinstance(callData, slicer.vtkMRMLModelNode):
            callData.AddObserver(callData.DisplayModifiedEvent, self.anglePlanes.onChangeModelDisplay)
            self.addObserver(callData, callData.PolyDataModifiedEvent, self.onModelNodePolyDataModified)
            self.anglePlanes.updateOnSurfaceCheckBoxes()

    @vtk.calldata_type(vtk.VTK_OBJECT)
    def nodeRemovedCallback(self, caller, eventId, callData):
        if isinstance(callData, slicer.vtkMRMLModelNode):
            self.removeObserver(callData, callData.PolyDataModifiedEvent, self.onModelNodePolyDataModified)
            callData.RemoveObservers(callData.DisplayModifiedEvent)
            self.anglePlanes.updateOnSurfaceCheckBoxes()
        if isinstance(callData, slicer.vtkMRMLMarkupsFiducialNode):
            name = callData.GetName()
            planeid = name[len('P'):]
            name = "Plane " + planeid
            if name in self.anglePlanes.planeControlsDictionary.keys():
                self.anglePlanes.RemoveManualPlane(planeid)

    def onModelNodePolyDataModified(self, caller, eventId):
        pass

class AnglePlanesMiddleFiducial():
    def __init__(self, P1, P2, onSurface, nodeID):
        self.P1 = P1
        self.P2 = P2
        self.onSurface = onSurface
        self.nodeID = nodeID

class AnglePlanes(ScriptedLoadableModule):
    def __init__(self, parent):

        ScriptedLoadableModule.__init__(self, parent)
        parent.title = "Angle Planes"
        parent.categories = ["Shape Analysis"]
        parent.dependencies = []
        parent.contributors = ["Julia Lopinto", "Juan Carlos Prieto", "Francois Budin", "Jean-Baptiste Vimort"]
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
        self.logic = AnglePlanesLogic(interface=self)
        self.planeControlsId = 0
        self.planeControlsDictionary = {}
        self.planeCollection = vtk.vtkPlaneCollection()
        self.ignoredNodeNames = ('Red Volume Slice', 'Yellow Volume Slice', 'Green Volume Slice')
        self.colorSliceVolumes = dict()
        self.n_vector = numpy.matrix([[0], [0], [1], [1]])

        self.interactionNode = slicer.mrmlScene.GetNodeByID("vtkMRMLInteractionNodeSingleton")
        # Definition of the 2 planes

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

        self.autoChangeLayout = qt.QCheckBox()
        self.autoChangeLayout.setCheckState(qt.Qt.Checked)
        self.autoChangeLayout.setTristate(False)
        self.autoChangeLayout.setText("Automatically change layout to 3D only")
        self.loadFormLayout.addWidget(self.autoChangeLayout)
        # Add vertical spacer
        self.layout.addStretch(1)
        #------------------------ Compute Bounding Box ----------------------#
        buttonFrameBox = qt.QFrame(self.parent)
        buttonFrameBox.setLayout(qt.QHBoxLayout())
        self.loadFormLayout.addWidget(buttonFrameBox)

        self.computeBox = qt.QPushButton("Compute Bounding Box around all models")
        buttonFrameBox.layout().addWidget(self.computeBox)
        self.computeBox.connect('clicked()', self.onComputeBox)
        self.computeBox.setDisabled(True)
        self.CollapsibleButton = ctk.ctkCollapsibleButton()
        self.CollapsibleButton.text = "Manage planes"
        self.layout.addWidget(self.CollapsibleButton)
        self.managePlanesFormLayout = qt.QFormLayout(self.CollapsibleButton)
        self.CollapsibleButton.checked = True

        # Add planes and manage landmark addition to each plane

        # -------------------------------Selection of a model for new plan---------------------------------
        # Input model Selectors
        inputModelLabel = qt.QLabel("Model for projection")
        self.inputModelSelector = slicer.qMRMLNodeComboBox()
        self.inputModelSelector.objectName = 'inputFixedModelNodeSelector'
        self.inputModelSelector.nodeTypes = ['vtkMRMLModelNode']
        self.inputModelSelector.selectNodeUponCreation = False
        self.inputModelSelector.addEnabled = False
        self.inputModelSelector.removeEnabled = False
        self.inputModelSelector.noneEnabled = True
        self.inputModelSelector.showHidden = False
        self.inputModelSelector.showChildNodeTypes = False
        self.inputModelSelector.setMRMLScene(slicer.mrmlScene)
        # Input landmark Selector
        inputLandmarksLabel = qt.QLabel("Connected landmarks")
        self.inputLandmarksSelector = slicer.qMRMLNodeComboBox()
        self.inputLandmarksSelector.objectName = 'inputMovingFiducialsNodeSelector'
        self.inputLandmarksSelector.nodeTypes = ['vtkMRMLMarkupsFiducialNode']
        self.inputLandmarksSelector.selectNodeUponCreation = True
        self.inputLandmarksSelector.addEnabled = True
        self.inputLandmarksSelector.removeEnabled = False
        self.inputLandmarksSelector.renameEnabled = True
        self.inputLandmarksSelector.noneEnabled = True
        self.inputLandmarksSelector.showHidden = False
        self.inputLandmarksSelector.showChildNodeTypes = True
        self.inputLandmarksSelector.setMRMLScene(slicer.mrmlScene)
        self.inputLandmarksSelector.setEnabled(False)
        # input landmarks Frames
        inputModelSelectorFrame = qt.QFrame(self.parent)
        inputModelSelectorFrame.setLayout(qt.QHBoxLayout())
        inputModelSelectorFrame.layout().addWidget(inputModelLabel)
        inputModelSelectorFrame.layout().addWidget(self.inputModelSelector)
        # Load on the surface
        self.loadLandmarksOnSurfacCheckBox = qt.QCheckBox("On Surface")
        self.loadLandmarksOnSurfacCheckBox.setChecked(True)
        # Layouts
        InputModelLayout = qt.QHBoxLayout()
        InputModelLayout.addWidget(inputModelSelectorFrame)
        # input landmarks Frames
        inputLandmarksSelectorFrame = qt.QFrame(self.parent)
        inputLandmarksSelectorFrame.setLayout(qt.QHBoxLayout())
        inputLandmarksSelectorFrame.layout().addWidget(inputLandmarksLabel)
        inputLandmarksSelectorFrame.layout().addWidget(self.inputLandmarksSelector)
        # Layouts
        InputLandmarkLayout = qt.QHBoxLayout()
        InputLandmarkLayout.addWidget(inputLandmarksSelectorFrame)
        InputLandmarkLayout.addWidget(self.loadLandmarksOnSurfacCheckBox)
        # Add plan Button
        self.addPlaneButton = qt.QPushButton(qt.QIcon(":/Icons/MarkupsAddFiducial.png"), " ")
        self.addPlaneButton.connect('clicked()', self.addNewPlane)
        self.addPlaneButton.setEnabled(False)
        # input GroupBox
        InputLayout = qt.QVBoxLayout()
        InputLayout.addLayout(InputModelLayout)
        InputLayout.addLayout(InputLandmarkLayout)
        InputLayout.addWidget(self.addPlaneButton)
        self.modelBox = qt.QGroupBox("Add new plan")
        self.modelBox.setLayout(InputLayout)
        self.managePlanesFormLayout.addRow(self.modelBox)
        # Select a landmark
        self.landmarkComboBox = qt.QComboBox()
        self.landmarkComboBox.connect('currentIndexChanged(QString)', self.UpdateInterface)
        BoxLayout = qt.QFormLayout()
        BoxLayout.addRow("Select a Landmark:", self.landmarkComboBox)
        self.surfaceDeplacementCheckBox = qt.QCheckBox(" deplacement on surface ")
        self.surfaceDeplacementCheckBox.setChecked(True)
        self.surfaceDeplacementCheckBox.connect('stateChanged(int)', self.onSurfaceDeplacementStateChanged)
        scaleAndAddLandmarkLayout = qt.QHBoxLayout()
        scaleAndAddLandmarkLayout.addLayout(BoxLayout)
        scaleAndAddLandmarkLayout.addWidget(self.surfaceDeplacementCheckBox)
        self.modelBox2 = qt.QGroupBox("Landmark modification")
        self.modelBox2.setLayout(scaleAndAddLandmarkLayout)
        self.managePlanesFormLayout.addRow(self.modelBox2)

        #        ----------------- Compute Mid Point -------------   
        self.midPointGroupBox = ctk.ctkCollapsibleButton()
        landmark1Layout = qt.QFormLayout()
        self.midPointGroupBox.setText('Define middle point between two landmarks')
        self.midPointGroupBox.collapsed = True
        self.parent.layout().addWidget(self.midPointGroupBox)
        self.selectPlaneForMidPoint = qt.QComboBox()
        self.selectPlaneForMidPoint.connect('currentIndexChanged(int)', self.onChangeMiddlePointFiducialNode)
        landmark1Layout.addRow('Choose plane: ', self.selectPlaneForMidPoint)
        self.landmarkComboBox1MidPoint = qt.QComboBox()
        self.landmarkComboBox2MidPoint = qt.QComboBox()
        landmark1Layout.addRow('Landmark A: ', self.landmarkComboBox1MidPoint)
        landmark1Layout.addRow('Landmark B: ', self.landmarkComboBox2MidPoint)
        self.midPointOnSurfaceCheckBox = qt.QCheckBox('On Surface')
        self.defineMiddlePointButton = qt.QPushButton(' Add middle point ')
        self.defineMiddlePointButton.setSizePolicy(3,1)
        middlePointLayout = qt.QHBoxLayout()
        middlePointLayout.addWidget(self.defineMiddlePointButton)
        middlePointLayout.addWidget(self.midPointOnSurfaceCheckBox)
        landmark1Layout.addRow(middlePointLayout)
        self.midPointGroupBox.setLayout(landmark1Layout)
        self.midPointGroupBox.setDisabled(True)
        self.defineMiddlePointButton.connect('clicked()', self.onAddMidPoint)

        # -------- Calculate angles between planes ------------

        self.CollapsibleButtonPlane = ctk.ctkCollapsibleButton()
        self.CollapsibleButtonPlane.text = "Choose planes"
        self.layout.addWidget(self.CollapsibleButtonPlane)
        sampleFormLayoutPlane = qt.QFormLayout(self.CollapsibleButtonPlane)

        self.planeComboBox1 = qt.QComboBox()
        self.fillColorsComboBox(self.planeComboBox1)
        sampleFormLayoutPlane.addRow("Select plane 1: ", self.planeComboBox1)

        self.planeComboBox2 = qt.QComboBox()
        self.fillColorsComboBox(self.planeComboBox2)
        sampleFormLayoutPlane.addRow("Select plane 2: ", self.planeComboBox2)

        self.CollapsibleButton2 = ctk.ctkCollapsibleButton()
        self.CollapsibleButton2.text = "Results"
        self.layout.addWidget(self.CollapsibleButton2)
        sampleFormLayout2 = qt.QVBoxLayout()
        self.CollapsibleButton2.setLayout(sampleFormLayout2)

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
        self.inputModelSelector.connect('currentNodeChanged(vtkMRMLNode*)', self.onModelChanged)
        self.inputLandmarksSelector.connect('currentNodeChanged(vtkMRMLNode*)', self.onLandmarksChanged)
        self.planeComboBox1.connect('currentIndexChanged(QString)', self.valueComboBox)
        self.planeComboBox2.connect('currentIndexChanged(QString)', self.valueComboBox)
        # Setting combo boxes at different values/index otherwise infinite loop
        self.planeComboBox1.setCurrentIndex(0)
        self.planeComboBox2.setCurrentIndex(0)
        self.valueComboBox()

        save.connect('clicked(bool)', self.onSavePlanes)
        read.connect('clicked(bool)', self.onReadPlanes)

        slicer.mrmlScene.AddObserver(slicer.mrmlScene.EndCloseEvent, self.onCloseScene)

        for i in self.getPositionOfModelNodes(False):
            modelnode = slicer.mrmlScene.GetNthNodeByClass(i, "vtkMRMLModelNode")
            modelnode.AddObserver(modelnode.DisplayModifiedEvent, self.onChangeModelDisplay)
        ModelAddedClass(self)

    def UpdateInterface(self):
        self.logic.UpdateThreeDView(self.landmarkComboBox.currentText)

    def onModelChanged(self):
        print "-------Model Changed--------"
        if self.logic.selectedModel:
            Model = self.logic.selectedModel
            try:
                Model.RemoveObserver(self.logic.decodeJSON(self.logic.selectedModel.GetAttribute("modelModifieTagEvent")))
            except:
                pass
        self.logic.selectedModel = self.inputModelSelector.currentNode()
        self.logic.ModelChanged(self.inputModelSelector, self.inputLandmarksSelector)
        self.inputLandmarksSelector.setCurrentNode(None)
        self.addPlaneButton.setEnabled(False)

    def onLandmarksChanged(self):
        print "-------Landmarks Changed--------"
        if self.inputModelSelector.currentNode():
            self.logic.FidList = self.inputLandmarksSelector.currentNode()
            self.logic.selectedFidList = self.inputLandmarksSelector.currentNode()
            self.logic.selectedModel = self.inputModelSelector.currentNode()
            if self.inputLandmarksSelector.currentNode():
                onSurface = self.loadLandmarksOnSurfacCheckBox.isChecked()
                self.logic.connectLandmarks(self.inputModelSelector,
                                      self.inputLandmarksSelector,
                                      onSurface)
                self.addPlaneButton.setEnabled(True)
            else:
                self.addPlaneButton.setEnabled(False)
                self.landmarkComboBox.clear()

    def onSurfaceDeplacementStateChanged(self):
        activeInput = self.logic.selectedModel
        if not activeInput:
            return
        fidList = self.logic.selectedFidList
        if not fidList:
            return
        selectedFidReflID = self.logic.findIDFromLabel(fidList, self.landmarkComboBox.currentText)
        isOnSurface = self.surfaceDeplacementCheckBox.isChecked()
        landmarkDescription = self.logic.decodeJSON(fidList.GetAttribute("landmarkDescription"))
        if isOnSurface:
            hardenModel = slicer.app.mrmlScene().GetNodeByID(fidList.GetAttribute("hardenModelID"))
            landmarkDescription[selectedFidReflID]["projection"]["isProjected"] = True
            landmarkDescription[selectedFidReflID]["projection"]["closestPointIndex"] =\
                self.logic.projectOnSurface(hardenModel, fidList, selectedFidReflID)
        else:
            landmarkDescription[selectedFidReflID]["projection"]["isProjected"] = False
            landmarkDescription[selectedFidReflID]["projection"]["closestPointIndex"] = None
            landmarkDescription[selectedFidReflID]["ROIradius"] = 0
        fidList.SetAttribute("landmarkDescription",self.logic.encodeJSON(landmarkDescription))

    def onChangeMiddlePointFiducialNode(self):
        key = self.selectPlaneForMidPoint.currentText
        if key is "":
            return
        plane = self.planeControlsDictionary[key]
        fidList = plane.fidlist
        self.logic.updateLandmarkComboBox(fidList, self.landmarkComboBox1MidPoint)
        self.logic.updateLandmarkComboBox(fidList, self.landmarkComboBox2MidPoint)

    def onChangeModelDisplay(self, obj, event):
        self.updateOnSurfaceCheckBoxes()

    def fillColorsComboBox(self, planeComboBox):
        planeComboBox.clear()
        planeComboBox.addItem("None")
        planeComboBox.addItem("Red")
        planeComboBox.addItem("Yellow")
        planeComboBox.addItem("Green")
        try:
            for x in self.planeControlsDictionary.keys():
                if self.planeControlsDictionary[x].PlaneIsDefined():
                    planeComboBox.addItem(x)
        except NameError:
            dummy = None

    def updateOnSurfaceCheckBoxes(self):
        numberOfVisibleModels = len(self.getPositionOfModelNodes(True))
        if numberOfVisibleModels > 0:
            self.computeBox.setDisabled(False)
        else:
            self.computeBox.setDisabled(True)

    def getPositionOfModelNodes(self, onlyVisible):
        numNodes = slicer.mrmlScene.GetNumberOfNodesByClass("vtkMRMLModelNode")
        positionOfNodes = list()
        for i in range(0, numNodes):
            node = slicer.mrmlScene.GetNthNodeByClass(i, "vtkMRMLModelNode")
            if node.GetName() in self.ignoredNodeNames:
                continue
            if onlyVisible is True and node.GetDisplayVisibility() == 0:
                continue
            positionOfNodes.append(i)
        return positionOfNodes

    def addNewPlane(self, keyLoad=-1):
        print "------- New plane created -------"
        if keyLoad != -1:
            self.planeControlsId = keyLoad
        else:
            self.planeControlsId += 1
        # if len(self.planeControlsDictionary) >= 1:
        #     self.addPlaneButton.setDisabled(True)
        planeControls = AnglePlanesWidgetPlaneControl(self,
                                                      self.planeControlsId,
                                                      self.planeCollection,
                                                      self.inputLandmarksSelector.currentNode())
        self.managePlanesFormLayout.addRow(planeControls)

        key = "Plane " + str(self.planeControlsId)
        self.planeControlsDictionary[key] = planeControls
        self.updatePlanesComboBoxes()
        self.midPointGroupBox.setDisabled(False)
        self.selectPlaneForMidPoint.addItem(key)

    def RemoveManualPlane(self, id):
        print "--- Remove a plan ---"
        key = "Plane " + str(id)
        # If the plane has already been removed (for example, when removing this plane in this function,
        # the callback on removing the nodes will be called, and therefore this function will be called again
        # We need to not do anything the second time this function is called for the same plane
        if key not in self.planeControlsDictionary.keys():
            print "Key error"
            return
        fiducialList = slicer.util.getNode('P' + str(id))
        planeControls = self.planeControlsDictionary[key]
        self.managePlanesFormLayout.removeWidget(planeControls)
        planeControls.deleteLater()
        planeControls.remove()
        self.planeControlsDictionary.pop(key)
        self.addPlaneButton.setDisabled(False)
        if len(self.planeControlsDictionary.keys()) == 0:
            self.midPointGroupBox.setDisabled(True)
            self.midPointGroupBox.collapsed = True
        self.updatePlanesComboBoxes()
        self.valueComboBox()
        if self.selectPlaneForMidPoint.findText(key) > -1:
            self.selectPlaneForMidPoint.removeItem(self.selectPlaneForMidPoint.findText(key))

    def onComputeBox(self):
        positionOfVisibleNodes = self.getPositionOfModelNodes(True)
        if len(positionOfVisibleNodes) == 0:
            return
        try:
            maxValue = slicer.sys.float_info.max
        except:
            maxValue = self.logic.sys.float_info.max
        bound = [maxValue, -maxValue, maxValue, -maxValue, maxValue, -maxValue]
        for i in positionOfVisibleNodes:
            node = slicer.mrmlScene.GetNthNodeByClass(i, "vtkMRMLModelNode")
            polydata = node.GetPolyData()
            if polydata is None or not hasattr(polydata, "GetBounds"):
                continue
            tempbound = polydata.GetBounds()
            bound[0] = min(bound[0], tempbound[0])
            bound[2] = min(bound[2], tempbound[2])
            bound[4] = min(bound[4], tempbound[4])

            bound[1] = max(bound[1], tempbound[1])
            bound[3] = max(bound[3], tempbound[3])
            bound[5] = max(bound[5], tempbound[5])
        # --------------------------- Box around the model --------------------------#
        dim = []
        origin = []
        for x in range(0, 3):
            dim.append(bound[x * 2 + 1] - bound[x * 2])
            origin.append(bound[x * 2] + dim[x] / 2)
            dim[x] *= 1.1
        # ---------definition of planes for clipping around the bounding box ---------#
        self.planeCollection = vtk.vtkPlaneCollection()
        self.planeXmin = vtk.vtkPlane()
        self.planeXmin.SetOrigin(bound[0],bound[2],bound[4])
        self.planeXmin.SetNormal(1,0,0)
        self.planeCollection.AddItem(self.planeXmin)
        self.planeYmin = vtk.vtkPlane()
        self.planeYmin.SetOrigin(bound[0],bound[2],bound[4])
        self.planeYmin.SetNormal(0,1,0)
        self.planeCollection.AddItem(self.planeYmin)
        self.planeZmin = vtk.vtkPlane()
        self.planeZmin.SetOrigin(bound[0],bound[2],bound[4])
        self.planeZmin.SetNormal(0,0,1)
        self.planeCollection.AddItem(self.planeZmin)
        self.planeXmax = vtk.vtkPlane()
        self.planeXmax.SetOrigin(bound[1],bound[3],bound[5])
        self.planeXmax.SetNormal(-1,0,0)
        self.planeCollection.AddItem(self.planeXmax)
        self.planeYmax = vtk.vtkPlane()
        self.planeYmax.SetOrigin(bound[1],bound[3],bound[5])
        self.planeYmax.SetNormal(0,-1,0)
        self.planeCollection.AddItem(self.planeYmax)
        self.planeZmax = vtk.vtkPlane()
        self.planeZmax.SetOrigin(bound[1],bound[3],bound[5])
        self.planeZmax.SetNormal(0,0,-1)
        self.planeCollection.AddItem(self.planeZmax)
        # print self.planeCollection
        dictColors = {'Red': 32, 'Yellow': 15, 'Green': 1}
        for x in dictColors.keys():
            sampleVolumeNode = self.CreateNewNode(x, dictColors[x], dim, origin)
            compNode = slicer.util.getNode('vtkMRMLSliceCompositeNode' + x)
            compNode.SetLinkedControl(False)
            compNode.SetBackgroundVolumeID(sampleVolumeNode.GetID())
            # print "set background" + x
        lm = slicer.app.layoutManager()
        #Reset and fit 2D-views
        lm.resetSliceViews()
        for x in dictColors.keys():
            logic = lm.sliceWidget(x)
            node = logic.mrmlSliceNode()
            node.SetSliceResolutionMode(node.SliceResolutionMatch2DView)
            logic.fitSliceToBackground()
        #Reset pink box around models
        for i in range(0, lm.threeDViewCount):
            threeDView = lm.threeDWidget(i).threeDView()
            threeDView.resetFocalPoint()
            #Reset camera in 3D view to center the models and position the camera so that all actors can be seen
            threeDView.renderWindow().GetRenderers().GetFirstRenderer().ResetCamera()

    def CreateNewNode(self, colorName, color, dim, origin):
        # we add a pseudo-random number to the name of our empty volume to avoid the risk of having a volume called
        #  exactly the same by the user which could be confusing. We could also have used slicer.app.sessionId()
        if colorName not in self.colorSliceVolumes.keys():
            VolumeName = "AnglePlanes_EmptyVolume_" + str(slicer.app.applicationPid()) + "_" + colorName
            # Do NOT set the spacing and the origin of imageData (vtkImageData)
            # The spacing and the origin should only be set in the vtkMRMLScalarVolumeNode!!!!!!
            # We only create an image of 1 voxel (as we only use it to color the planes
            imageData = vtk.vtkImageData()
            imageData.SetDimensions(1, 1, 1)
            imageData.AllocateScalars(vtk.VTK_UNSIGNED_CHAR, 1)
            imageData.SetScalarComponentFromDouble(0, 0, 0, 0, color)
            if hasattr(slicer, 'vtkMRMLLabelMapVolumeNode'):
                sampleVolumeNode = slicer.vtkMRMLLabelMapVolumeNode()
            else:
                sampleVolumeNode = slicer.vtkMRMLScalarVolumeNode()
            sampleVolumeNode = slicer.mrmlScene.AddNode(sampleVolumeNode)
            sampleVolumeNode.SetName(VolumeName)
            labelmapVolumeDisplayNode = slicer.vtkMRMLLabelMapVolumeDisplayNode()
            slicer.mrmlScene.AddNode(labelmapVolumeDisplayNode)
            colorNode = slicer.util.getNode('GenericAnatomyColors')
            labelmapVolumeDisplayNode.SetAndObserveColorNodeID(colorNode.GetID())
            sampleVolumeNode.SetAndObserveImageData(imageData)
            sampleVolumeNode.SetAndObserveDisplayNodeID(labelmapVolumeDisplayNode.GetID())
            labelmapVolumeDisplayNode.VisibilityOn()
            self.colorSliceVolumes[colorName] = sampleVolumeNode.GetID()
        sampleVolumeNode = slicer.mrmlScene.GetNodeByID(self.colorSliceVolumes[colorName])
        sampleVolumeNode.SetOrigin(origin[0], origin[1], origin[2])
        sampleVolumeNode.SetSpacing(dim[0], dim[1], dim[2])
        if not hasattr(slicer, 'vtkMRMLLabelMapVolumeNode'):
            sampleVolumeNode.SetLabelMap(1)
        sampleVolumeNode.SetHideFromEditors(True)
        sampleVolumeNode.SetSaveWithScene(False)
        return sampleVolumeNode

    def onAddMidPoint(self):
        key = self.selectPlaneForMidPoint.currentText
        plane = self.planeControlsDictionary[key]
        fidList = plane.fidlist
        if not fidList:
            self.logic.warningMessage("Fiducial list problem.")
        landmark1ID = self.logic.findIDFromLabel(fidList,self.landmarkComboBox1MidPoint.currentText)
        landmark2ID = self.logic.findIDFromLabel(fidList,self.landmarkComboBox2MidPoint.currentText)
        coord = self.logic.calculateMidPointCoord(fidList, landmark1ID, landmark2ID)
        fidList.AddFiducial(coord[0],coord[1],coord[2])
        fidList.SetNthFiducialSelected(fidList.GetNumberOfMarkups() - 1, False)
        # update of the data structure
        landmarkDescription = self.logic.decodeJSON(fidList.GetAttribute("landmarkDescription"))
        numOfMarkups = fidList.GetNumberOfMarkups()
        markupID = fidList.GetNthMarkupID(numOfMarkups - 1)
        landmarkDescription[landmark1ID]["midPoint"]["definedByThisMarkup"].append(markupID)
        landmarkDescription[landmark2ID]["midPoint"]["definedByThisMarkup"].append(markupID)
        landmarkDescription[markupID]["midPoint"]["isMidPoint"] = True
        landmarkDescription[markupID]["midPoint"]["Point1"] = landmark1ID
        landmarkDescription[markupID]["midPoint"]["Point2"] = landmark2ID
        if self.midPointOnSurfaceCheckBox.isChecked():
            landmarkDescription[markupID]["projection"]["isProjected"] = True
            hardenModel = slicer.app.mrmlScene().GetNodeByID(fidList.GetAttribute("hardenModelID"))
            landmarkDescription[markupID]["projection"]["closestPointIndex"] = \
                self.logic.projectOnSurface(hardenModel, fidList, markupID)
        else:
            landmarkDescription[markupID]["projection"]["isProjected"] = False
        fidList.SetAttribute("landmarkDescription",self.logic.encodeJSON(landmarkDescription))
        self.logic.interface.UpdateInterface()
        self.logic.updateLandmarkComboBox(fidList, self.landmarkComboBox, False)

    def onCloseScene(self, obj, event):
        self.colorSliceVolumes = dict()
        list = slicer.mrmlScene.GetNodesByClass("vtkMRMLModelNode")
        end = list.GetNumberOfItems()
        for i in range(0,end):
            model = list.GetItemAsObject(i)
            hardenModel = slicer.mrmlScene.GetNodesByName(model.GetName()).GetItemAsObject(0)
            slicer.mrmlScene.RemoveNode(hardenModel)
        keys = self.planeControlsDictionary.keys()
        for x in keys:
            self.RemoveManualPlane(x[len('Plane '):])
        self.planeControlsDictionary = dict()
        self.addPlaneButton.setDisabled(True)
            # globals()[self.moduleName] = slicer.util.reloadScriptedModule(self.moduleName)

    def angleValue(self):
        self.valueComboBox()
        self.getAngle_RL.setText(self.logic.angle_degre_RL)
        self.getAngle_RL_comp.setText(self.logic.angle_degre_RL_comp)
        self.getAngle_SI.setText(self.logic.angle_degre_SI)
        self.getAngle_SI_comp.setText(self.logic.angle_degre_SI_comp)
        self.getAngle_AP.setText(self.logic.angle_degre_AP)
        self.getAngle_AP_comp.setText(self.logic.angle_degre_AP_comp)

    def setFirstItemInComboBoxNotGivenString(self, comboBox, oldString, noThisString):
        if comboBox.findText(oldString) == -1:
            comboBox.setCurrentIndex(1)
        else:
            comboBox.setCurrentIndex(comboBox.findText(oldString))

    def updatePlanesComboBoxes(self):
        print "---- update plane combobox ----"
        self.planeComboBox1.blockSignals(True)
        self.planeComboBox2.blockSignals(True)
        colorPlane1 = self.planeComboBox1.currentText
        colorPlane2 = self.planeComboBox2.currentText
        # Reset Combo boxes
        self.fillColorsComboBox(self.planeComboBox1)
        self.fillColorsComboBox(self.planeComboBox2)
        if colorPlane1 != "None":
            self.planeComboBox2.removeItem(self.planeComboBox2.findText(colorPlane1))
        if colorPlane2 != "None":
            self.planeComboBox1.removeItem(self.planeComboBox1.findText(colorPlane2))
        self.setFirstItemInComboBoxNotGivenString(self.planeComboBox1, colorPlane1, colorPlane2)
        self.setFirstItemInComboBoxNotGivenString(self.planeComboBox2, colorPlane2, colorPlane1)
        self.planeComboBox1.blockSignals(False)
        self.planeComboBox2.blockSignals(False)

    def valueComboBox(self):
        self.updatePlanesComboBoxes()
        # Hide everything before showing what is necessary
        for x in self.logic.ColorNodeCorrespondence.keys():
            compNode = slicer.util.getNode('vtkMRMLSliceCompositeNode' + x)
            compNode.SetLinkedControl(False)
            slice = slicer.mrmlScene.GetNodeByID(self.logic.ColorNodeCorrespondence[x])
            slice.SetWidgetVisible(False)
            slice.SetSliceVisible(False)
        colorPlane1 = self.planeComboBox1.currentText
        colorPlane2 = self.planeComboBox2.currentText
        self.defineAngle(colorPlane1, colorPlane2)

    def defineAngle(self, colorPlane1, colorPlane2):
        # print colorPlane1
        if colorPlane1 != "None":
            if colorPlane1 in self.logic.ColorNodeCorrespondence:
                slice1 = slicer.util.getNode(self.logic.ColorNodeCorrespondence[colorPlane1])
                self.logic.getMatrix(slice1)
                slice1.SetWidgetVisible(True)
                slice1.SetSliceVisible(True)
                matrix1 = self.logic.getMatrix(slice1)
                normal1 = self.logic.defineNormal(matrix1)
            else:
                normal1 = self.planeControlsDictionary[colorPlane1].logic.N
        else:
            return
        # print colorPlane2
        if colorPlane2 != "None":
            if colorPlane2 in self.logic.ColorNodeCorrespondence:
                slice2 = slicer.util.getNode(self.logic.ColorNodeCorrespondence[colorPlane2])
                self.logic.getMatrix(slice2)
                slice2.SetWidgetVisible(True)
                slice2.SetSliceVisible(True)
                matrix2 = self.logic.getMatrix(slice2)
                normal2 = self.logic.defineNormal(matrix2)
            else:
                normal2 = self.planeControlsDictionary[colorPlane2].logic.N
        else:
            return
        self.logic.getAngle(normal1, normal2)

    def onSavePlanes(self):
        self.savePlanes()

    def savePlanes(self, filename=None):
        tempDictionary = {}
        sliceRed = slicer.util.getNode(self.logic.ColorNodeCorrespondence['Red'])
        tempDictionary["Red"] = self.logic.getMatrix(sliceRed).tolist()
        sliceYellow = slicer.util.getNode(self.logic.ColorNodeCorrespondence['Yellow'])
        tempDictionary["Yellow"] = self.logic.getMatrix(sliceYellow).tolist()
        sliceGreen = slicer.util.getNode(self.logic.ColorNodeCorrespondence['Green'])
        tempDictionary["Green"] = self.logic.getMatrix(sliceGreen).tolist()
        if filename is None:
            filename = qt.QFileDialog.getSaveFileName(parent=self, caption='Save file')
        if filename != "":
            fileObj = open(filename, "wb")
            pickle.dump(tempDictionary, fileObj)
            fileObj.close()

    def onReadPlanes(self):
        self.readPlanes()
        self.onComputeBox()

    def readPlanes(self, filename=None):
        if filename is None:
            filename = qt.QFileDialog.getOpenFileName(parent=self, caption='Open file')
        if filename != "":
            fileObj = open(filename, "rb")
            tempDictionary = pickle.load(fileObj)
            node = slicer.mrmlScene.GetNodeByID('vtkMRMLSliceNodeRed')
            matList = tempDictionary["Red"]
            matNode = node.GetSliceToRAS()
            for col in range(0, len(matList)):
                for row in range(0, len(matList[col])):
                    matNode.SetElement(col, row, matList[col][row])
            node = slicer.mrmlScene.GetNodeByID('vtkMRMLSliceNodeYellow')
            matList = tempDictionary["Yellow"]
            matNode = node.GetSliceToRAS()
            for col in range(0, len(matList)):
                for row in range(0, len(matList[col])):
                    matNode.SetElement(col, row, matList[col][row])
            node = slicer.mrmlScene.GetNodeByID('vtkMRMLSliceNodeGreen')
            matList = tempDictionary["Green"]
            matNode = node.GetSliceToRAS()
            for col in range(0, len(matList)):
                for row in range(0, len(matList[col])):
                    matNode.SetElement(col, row, matList[col][row])
            fileObj.close()


# This widget controls each of the planes that are added to the interface.
# The widget contains its own logic, i.e. an object of AnglePlanesLogic. 
# Each plane contains a separate fiducial list. The planes are named P1, P2, ..., PN. The landmarks are named
# P1-1, P1-2, P1-N. 
class AnglePlanesWidgetPlaneControl(qt.QFrame):
    def __init__(self, anglePlanes, id, planeCollection, fidlist):
        # ------------- variables -------------------
        self.anglePlanes = anglePlanes
        self.logic = anglePlanes.logic
        self.planeCollection = planeCollection
        self.id = id
        self.fidlist = fidlist
        self.actor = vtk.vtkActor()
        # -------------- interface -------------------
        qt.QFrame.__init__(self)
        self.setLayout(qt.QFormLayout())
        landmarkLayout = qt.QVBoxLayout()
        planeLabelLayout = qt.QHBoxLayout()
        planeLabel = qt.QLabel('Plane ' + str(id) + ":")
        planeLabelLayout.addWidget(planeLabel)
        planeLabelLayout.addStretch()
        addFiducialLabel = qt.QLabel('Add')
        addFiducialButton = qt.QPushButton(qt.QIcon(":/Icons/AnnotationPointWithArrow.png"), " ")
        addFiducialButton.setFixedSize(50, 25)
        addFiducialButton.connect('clicked()', self.addLandMarkClicked)
        addFiducialButton.setEnabled(True)
        planeLabelLayout.addWidget(addFiducialLabel)
        planeLabelLayout.addWidget(addFiducialButton)
        landmarkLayout.addLayout(planeLabelLayout)
        label1Layout = qt.QHBoxLayout()

        label1 = qt.QLabel(' L1:')
        self.landmark1ComboBox = qt.QComboBox()
        landmark1ComboBox = self.landmark1ComboBox
        landmark1ComboBox.addItem("Select")
        landmark1ComboBox.connect('currentIndexChanged(QString)', self.placePlaneClicked)
        label1Layout.addWidget(label1)
        label1Layout.addWidget(landmark1ComboBox)
        landmarkLayout.addLayout(label1Layout)
        label2Layout = qt.QHBoxLayout()

        label2 = qt.QLabel(' L2:')
        self.landmark2ComboBox = qt.QComboBox()
        landmark2ComboBox = self.landmark2ComboBox
        landmark2ComboBox.addItem("Select")
        landmark2ComboBox.connect('currentIndexChanged(QString)', self.placePlaneClicked)
        label2Layout.addWidget(label2)
        label2Layout.addWidget(landmark2ComboBox)
        landmarkLayout.addLayout(label2Layout)
        label3Layout = qt.QHBoxLayout()

        label3 = qt.QLabel(' L3:')
        self.landmark3ComboBox = qt.QComboBox()
        landmark3ComboBox = self.landmark3ComboBox
        landmark3ComboBox.addItem("Select")
        landmark3ComboBox.connect('currentIndexChanged(QString)', self.placePlaneClicked)
        label3Layout.addWidget(label3)
        label3Layout.addWidget(landmark3ComboBox)
        landmarkLayout.addLayout(label3Layout)

        self.layout().addRow(landmarkLayout)

        self.slideOpacity = ctk.ctkSliderWidget()
        slideOpacity = self.slideOpacity
        slideOpacity.singleStep = 0.1
        slideOpacity.minimum = 0.1
        slideOpacity.maximum = 1
        slideOpacity.value = 1.0
        slideOpacity.toolTip = "Set the opacity of your plane."

        slideOpacity.connect('valueChanged(double)', self.placePlaneClicked)

        landmarkSliderLayout = qt.QHBoxLayout()

        label2 = qt.QLabel(' Opacity:')

        landmarkSliderLayout.addWidget(label2)
        landmarkSliderLayout.addWidget(self.slideOpacity)

        self.AdaptToBoundingBoxCheckBox = qt.QCheckBox("Adapt to bounding box")
        self.AdaptToBoundingBoxCheckBox.setChecked(False)
        self.AdaptToBoundingBoxCheckBox.connect('stateChanged(int)', self.onBBox)
        landmarkSliderLayout.addWidget(self.AdaptToBoundingBoxCheckBox)
        self.AdaptToBoundingBoxCheckBox.connect('stateChanged(int)',self.placePlaneClicked)

        self.HidePlaneCheckBox = qt.QCheckBox("Hide")
        self.HidePlaneCheckBox.setChecked(False)
        self.HidePlaneCheckBox.connect('stateChanged(int)', self.update)
        landmarkSliderLayout.addWidget(self.HidePlaneCheckBox)

        self.layout().addRow(landmarkSliderLayout)

        removeButtonLayout = qt.QHBoxLayout()
        removeButtonLayout.addStretch(1)
        removePlaneButton = qt.QPushButton("Remove Plane")
        removeButtonLayout.addWidget(removePlaneButton)
        self.layout().addRow(removeButtonLayout)
        removePlaneButton.connect('clicked(bool)', self.onRemove)

        # fiducial list for the plane
        self.logic.updateLandmarkComboBox(self.fidlist, self.landmark1ComboBox)
        self.logic.updateLandmarkComboBox(self.fidlist, self.landmark2ComboBox)
        self.logic.updateLandmarkComboBox(self.fidlist, self.landmark3ComboBox)


    def PlaneIsDefined(self):
        landmark1 = self.logic.findIDFromLabel(self.fidlist, self.landmark1ComboBox.currentText)
        landmark2 = self.logic.findIDFromLabel(self.fidlist, self.landmark2ComboBox.currentText)
        landmark3 = self.logic.findIDFromLabel(self.fidlist, self.landmark3ComboBox.currentText)
        if landmark1 and landmark2 and landmark3:
            if landmark1 != landmark2 \
                    and landmark3 != landmark2 \
                    and landmark3 != landmark1:
                return True
        return False

    def onRemove(self):
        self.anglePlanes.RemoveManualPlane(self.id)

    def getFiducials(self):

        listCoord = list()

        coord = numpy.zeros(3)
        self.fidlist.GetNthFiducialPosition(int(self.landmark1ComboBox.currentIndex) - 1, coord)
        listCoord.append(coord)

        self.fidlist.GetNthFiducialPosition(int(self.landmark2ComboBox.currentIndex) - 1, coord)
        listCoord.append(coord)

        self.fidlist.GetNthFiducialPosition(int(self.landmark3ComboBox.currentIndex) - 1, coord)
        listCoord.append(coord)

        return listCoord

    def placePlaneClicked(self):
        self.anglePlanes.valueComboBox()
        self.update()

    def onBBox(self):
        self.anglePlanes.onComputeBox()
        self.update()

    def update(self):
        self.planeCollection = self.anglePlanes.planeCollection
        if self.PlaneIsDefined():
            if self.HidePlaneCheckBox.isChecked():
                self.logic.planeLandmarks(self.fidlist,
                                          self.landmark1ComboBox.currentText, self.landmark2ComboBox.currentText,
                                          self.landmark3ComboBox.currentText, self.AdaptToBoundingBoxCheckBox,
                                          0, self.planeCollection, self.actor)
            else:
                self.logic.planeLandmarks(self.fidlist,
                                          self.landmark1ComboBox.currentText, self.landmark2ComboBox.currentText,
                                          self.landmark3ComboBox.currentText, self.AdaptToBoundingBoxCheckBox,
                                          self.slideOpacity.value, self.planeCollection, self.actor)

    def addLandMarkClicked(self):
        print "Add landmarks"
        self.anglePlanes.inputModelSelector.setCurrentNode(slicer.app.mrmlScene().GetNodeByID(self.fidlist.GetAttribute("connectedModelID")))
        self.anglePlanes.inputLandmarksSelector.setCurrentNode(self.fidlist)
        # Place landmarks in the 3D scene
        selectionNode = slicer.mrmlScene.GetNodeByID("vtkMRMLSelectionNodeSingleton")
        selectionNode.SetReferenceActivePlaceNodeClassName("vtkMRMLMarkupsFiducialNode")
        selectionNode.SetActivePlaceNodeID(self.fidlist.GetID())
        # print selectionNode
        interactionNode = slicer.mrmlScene.GetNodeByID("vtkMRMLInteractionNodeSingleton")
        interactionNode.SetCurrentInteractionMode(1)
        # To select multiple points in the 3D view, we want to have to click
        # on the "place fiducial" button multiple times
        placeModePersistence = 0
        interactionNode.SetPlaceModePersistence(placeModePersistence)

    def remove(self):
        renderer = list()
        renderWindow = list()
        layoutManager = slicer.app.layoutManager()
        for i in range(0, layoutManager.threeDViewCount):
            threeDWidget = layoutManager.threeDWidget(i)
            threeDView = threeDWidget.threeDView()
            renderWindow.append(threeDView.renderWindow())
            renderers = renderWindow[i].GetRenderers()
            renderer.append(renderers.GetFirstRenderer())
            renderer[i].RemoveViewProp(self.actor)
            renderWindow[i].AddRenderer(renderer[i])
            renderer[i].Render()
        self.actor.RemoveAllObservers()
        self.actor = None

class AnglePlanesLogic(ScriptedLoadableModuleLogic):
    try:
        slicer.sys
    except:
        import sys

    def __init__(self, interface = None):
        self.ColorNodeCorrespondence = {'Red': 'vtkMRMLSliceNodeRed',
                                        'Yellow': 'vtkMRMLSliceNodeYellow',
                                        'Green': 'vtkMRMLSliceNodeGreen'}
        self.selectedFidList = None
        self.selectedModel = None
        self.interface = interface

    def UpdateThreeDView(self, landmarkLabel):
        # Update the 3D view on Slicer
        if not self.selectedFidList:
            return
        if not self.selectedModel:
            return
        print "UpdateThreeDView"
        active = self.selectedFidList
        #deactivate all landmarks
        list = slicer.mrmlScene.GetNodesByClass("vtkMRMLMarkupsFiducialNode")
        end = list.GetNumberOfItems()
        selectedFidReflID = self.findIDFromLabel(active,landmarkLabel)
        for i in range(0,end):
            fidList = list.GetItemAsObject(i)
            landmarkDescription = self.decodeJSON(fidList.GetAttribute("landmarkDescription"))
            for key in landmarkDescription.iterkeys():
                markupsIndex = fidList.GetMarkupIndexByID(key)
                if key != selectedFidReflID:
                    fidList.SetNthMarkupLocked(markupsIndex, True)
                else:
                    fidList.SetNthMarkupLocked(markupsIndex, False)
        displayNode = self.selectedModel.GetModelDisplayNode()
        displayNode.SetScalarVisibility(False)
        if selectedFidReflID != False:
            displayNode.SetScalarVisibility(True)

    def createIntermediateHardenModel(self, model):
        hardenModel = slicer.mrmlScene.GetNodesByName("SurfaceRegistration_" + model.GetName() + "_hardenCopy_" + str(
            slicer.app.applicationPid())).GetItemAsObject(0)
        if hardenModel is None:
            hardenModel = slicer.vtkMRMLModelNode()
        hardenPolyData = vtk.vtkPolyData()
        hardenPolyData.DeepCopy(model.GetPolyData())
        hardenModel.SetAndObservePolyData(hardenPolyData)
        hardenModel.SetName(
            "SurfaceRegistration_" + model.GetName() + "_hardenCopy_" + str(slicer.app.applicationPid()))
        if model.GetParentTransformNode():
            hardenModel.SetAndObserveTransformNodeID(model.GetParentTransformNode().GetID())
        hardenModel.HideFromEditorsOn()
        slicer.mrmlScene.AddNode(hardenModel)
        logic = slicer.vtkSlicerTransformLogic()
        logic.hardenTransform(hardenModel)
        return hardenModel

    def onModelModified(self, obj, event):
        #recompute the harden model
        hardenModel = self.createIntermediateHardenModel(obj)
        obj.SetAttribute("hardenModelID",hardenModel.GetID())
        # for each fiducial list
        list = slicer.mrmlScene.GetNodesByClass("vtkMRMLMarkupsFiducialNode")
        end = list.GetNumberOfItems()
        for i in range(0,end):
            # If landmarks are projected on the modified model
            fidList = list.GetItemAsObject(i)
            if fidList.GetAttribute("connectedModelID"):
                if fidList.GetAttribute("connectedModelID") == obj.GetID():
                    #replace the harden model with the new one
                    fidList.SetAttribute("hardenModelID",hardenModel.GetID())
                    #reproject the fiducials on the new model
                    landmarkDescription = self.decodeJSON(fidList.GetAttribute("landmarkDescription"))
                    for n in range(fidList.GetNumberOfMarkups()):
                        markupID = fidList.GetNthMarkupID(n)
                        if landmarkDescription[markupID]["projection"]["isProjected"] == True:
                            hardenModel = slicer.app.mrmlScene().GetNodeByID(fidList.GetAttribute("hardenModelID"))
                            markupsIndex = fidList.GetMarkupIndexByID(markupID)
                            self.replaceLandmark(hardenModel.GetPolyData(), fidList, markupsIndex,
                                                 landmarkDescription[markupID]["projection"]["closestPointIndex"])
                        fidList.SetAttribute("landmarkDescription",self.encodeJSON(landmarkDescription))

    def ModelChanged(self, inputModelSelector, inputLandmarksSelector):
        inputModel = inputModelSelector.currentNode()
        # if a Model Node is present
        if inputModel:
            self.selectedModel = inputModel
            hardenModel = self.createIntermediateHardenModel(inputModel)
            inputModel.SetAttribute("hardenModelID",hardenModel.GetID())
            modelModifieTagEvent = inputModel.AddObserver(inputModel.TransformModifiedEvent, self.onModelModified)
            inputModel.SetAttribute("modelModifieTagEvent",self.encodeJSON({'modelModifieTagEvent':modelModifieTagEvent}))
            inputLandmarksSelector.setEnabled(True)
        # if no model is selected
        else:
            # Update the fiducial list selector
            inputLandmarksSelector.setCurrentNode(None)
            inputLandmarksSelector.setEnabled(False)

    def isUnderTransform(self, markups):
        if markups.GetParentTransformNode():
            messageBox = ctk.ctkMessageBox()
            messageBox.setWindowTitle(" /!\ WARNING /!\ ")
            messageBox.setIcon(messageBox.Warning)
            messageBox.setText("Your Markup Fiducial Node is currently modified by a transform,"
                               "if you choose to continue the program will apply the transform"
                               "before doing anything else!")
            messageBox.setInformativeText("Do you want to continue?")
            messageBox.setStandardButtons(messageBox.No | messageBox.Yes)
            choice = messageBox.exec_()
            if choice == messageBox.Yes:
                logic = slicer.vtkSlicerTransformLogic()
                logic.hardenTransform(markups)
                return False
            else:
                messageBox.setText(" Node not modified")
                messageBox.setStandardButtons(messageBox.Ok)
                messageBox.setInformativeText("")
                messageBox.exec_()
                return True
        else:
            return False

    def connectedModelChangement(self):
        messageBox = ctk.ctkMessageBox()
        messageBox.setWindowTitle(" /!\ WARNING /!\ ")
        messageBox.setIcon(messageBox.Warning)
        messageBox.setText("The Markup Fiducial Node selected is curently projected on an"
                           "other model, if you chose to continue the fiducials will be  "
                           "reprojected, and this could impact the functioning of other modules")
        messageBox.setInformativeText("Do you want to continue?")
        messageBox.setStandardButtons(messageBox.No | messageBox.Yes)
        choice = messageBox.exec_()
        if choice == messageBox.Yes:
            return True
        else:
            messageBox.setText(" Node not modified")
            messageBox.setStandardButtons(messageBox.Ok)
            messageBox.setInformativeText("")
            messageBox.exec_()
            return False

    def createNewDataStructure(self,landmarks, model, onSurface):
        landmarks.SetAttribute("connectedModelID",model.GetID())
        landmarks.SetAttribute("hardenModelID",model.GetAttribute("hardenModelID"))
        landmarkDescription = dict()
        for n in range(landmarks.GetNumberOfMarkups()):
            markupID = landmarks.GetNthMarkupID(n)
            landmarkDescription[markupID] = dict()
            landmarkLabel = landmarks.GetName() + '-' + str(n + 1)
            landmarkDescription[markupID]["landmarkLabel"] = landmarkLabel
            landmarkDescription[markupID]["ROIradius"] = 0
            landmarkDescription[markupID]["projection"] = dict()
            if onSurface:
                landmarkDescription[markupID]["projection"]["isProjected"] = True
                hardenModel = slicer.app.mrmlScene().GetNodeByID(landmarks.GetAttribute("hardenModelID"))
                landmarkDescription[markupID]["projection"]["closestPointIndex"] = \
                    self.projectOnSurface(hardenModel, landmarks, markupID)
            else:
                landmarkDescription[markupID]["projection"]["isProjected"] = False
                landmarkDescription[markupID]["projection"]["closestPointIndex"] = None
            landmarkDescription[markupID]["midPoint"] = dict()
            landmarkDescription[markupID]["midPoint"]["definedByThisMarkup"] = list()
            landmarkDescription[markupID]["midPoint"]["isMidPoint"] = False
            landmarkDescription[markupID]["midPoint"]["Point1"] = None
            landmarkDescription[markupID]["midPoint"]["Point2"] = None
        landmarks.SetAttribute("landmarkDescription",self.encodeJSON(landmarkDescription))
        planeDescription = dict()
        landmarks.SetAttribute("planeDescription",self.encodeJSON(planeDescription))
        landmarks.SetAttribute("isClean",self.encodeJSON({"isClean":False}))
        landmarks.SetAttribute("lastTransformID",None)
        landmarks.SetAttribute("arrayName",model.GetName() + "_ROI")

    def changementOfConnectedModel(self,landmarks, model, onSurface):
        landmarks.SetAttribute("connectedModelID",model.GetID())
        landmarks.SetAttribute("hardenModelID",model.GetAttribute("hardenModelID"))
        landmarkDescription = self.decodeJSON(landmarks.GetAttribute("landmarkDescription"))
        for n in range(landmarks.GetNumberOfMarkups()):
            markupID = landmarks.GetNthMarkupID(n)
            if onSurface:
                if landmarkDescription[markupID]["projection"]["isProjected"] == True:
                    hardenModel = slicer.app.mrmlScene().GetNodeByID(landmarks.GetAttribute("hardenModelID"))
                    landmarkDescription[markupID]["projection"]["closestPointIndex"] = \
                        self.projectOnSurface(hardenModel, landmarks, markupID)
            else:
                landmarkDescription[markupID]["projection"]["isProjected"] = False
                landmarkDescription[markupID]["projection"]["closestPointIndex"] = None
            landmarks.SetAttribute("landmarkDescription",self.encodeJSON(landmarkDescription))
        landmarks.SetAttribute("isClean",self.encodeJSON({"isClean":False}))

    def connectLandmarks(self, modelSelector, landmarkSelector, onSurface):
        model = modelSelector.currentNode()
        landmarks = landmarkSelector.currentNode()
        self.selectedFidList = landmarks
        self.selectedModel = model
        if not (model and landmarks):
            return

        if self.isUnderTransform(landmarks):
            landmarkSelector.setCurrentNode(None)
            return
        connectedModelID = landmarks.GetAttribute("connectedModelID")
        try:
            tag = self.decodeJSON(landmarks.GetAttribute("MarkupAddedEventTag"))
            landmarks.RemoveObserver(tag["MarkupAddedEventTag"])
            print "adding observers removed!"
        except:
            pass
        try:
            tag = self.decodeJSON(landmarks.GetAttribute("PointModifiedEventTag"))
            landmarks.RemoveObserver(tag["PointModifiedEventTag"])
            print "moving observers removed!"
        except:
            pass
        try:
            tag = self.decodeJSON(landmarks.GetAttribute("MarkupRemovedEventTag"))
            landmarks.RemoveObserver(tag["MarkupRemovedEventTag"])
            print "removing observers removed!"
        except:
            pass
        try:
            tag = self.decodeJSON(landmarks.GetAttribute("UpdatesPlanesEventTag"))
            landmarks.RemoveObserver(tag["UpdatesPlanesEventTag"])
            print "Planes observers removed!"
        except:
            pass
        if connectedModelID:
            if connectedModelID != model.GetID():
                if self.connectedModelChangement():
                    self.changementOfConnectedModel(landmarks, model, onSurface)
                else:
                    landmarkSelector.setCurrentNode(None)
                    return
        # creation of the data structure
        else:
            self.createNewDataStructure(landmarks, model, onSurface)
        #update of the landmark Combo Box
        self.updateLandmarkComboBox(landmarks, self.interface.landmarkComboBox, False)
        #adding of listeners
        MarkupAddedEventTag = landmarks.AddObserver(landmarks.MarkupAddedEvent, self.onMarkupAddedEvent)
        landmarks.SetAttribute("MarkupAddedEventTag",self.encodeJSON({"MarkupAddedEventTag":MarkupAddedEventTag}))
        PointModifiedEventTag = landmarks.AddObserver(landmarks.PointModifiedEvent, self.onPointModifiedEvent)
        landmarks.SetAttribute("PointModifiedEventTag",self.encodeJSON({"PointModifiedEventTag":PointModifiedEventTag}))
        MarkupRemovedEventTag = landmarks.AddObserver(landmarks.MarkupRemovedEvent, self.onMarkupRemovedEvent)
        landmarks.SetAttribute("MarkupRemovedEventTag",self.encodeJSON({"MarkupRemovedEventTag":MarkupRemovedEventTag}))
        UpdatesPlanesEventTag = landmarks.AddObserver(landmarks.PointModifiedEvent, self.updatePlanesEvent)
        landmarks.SetAttribute("UpdatesPlanesEventTag",self.encodeJSON({"UpdatesPlanesEventTag":UpdatesPlanesEventTag}))

    # Called when a landmark is added on a model
    def onMarkupAddedEvent(self, obj, event):
        print "------markup adding-------"
        landmarkDescription = self.decodeJSON(obj.GetAttribute("landmarkDescription"))
        numOfMarkups = obj.GetNumberOfMarkups()
        markupID = obj.GetNthMarkupID(numOfMarkups - 1)
        landmarkDescription[markupID] = dict()
        landmarkLabel = obj.GetNthMarkupLabel(numOfMarkups - 1)
        landmarkDescription[markupID]["landmarkLabel"] = landmarkLabel
        landmarkDescription[markupID]["ROIradius"] = 0
        landmarkDescription[markupID]["projection"] = dict()
        landmarkDescription[markupID]["projection"]["isProjected"] = True
        # The landmark will be projected by onPointModifiedEvent
        landmarkDescription[markupID]["midPoint"] = dict()
        landmarkDescription[markupID]["midPoint"]["definedByThisMarkup"] = list()
        landmarkDescription[markupID]["midPoint"]["isMidPoint"] = False
        landmarkDescription[markupID]["midPoint"]["Point1"] = None
        landmarkDescription[markupID]["midPoint"]["Point2"] = None
        obj.SetAttribute("landmarkDescription",self.encodeJSON(landmarkDescription))
        self.updateAllLandmarkComboBox(obj, markupID)
        self.interface.UpdateInterface()

    def updateMidPoint(self, fidList, landmarkID):
        landmarkDescription = self.decodeJSON(fidList.GetAttribute("landmarkDescription"))
        for midPointID in landmarkDescription[landmarkID]["midPoint"]["definedByThisMarkup"]:
            if landmarkDescription[midPointID]["midPoint"]["isMidPoint"]:
                landmark1ID = landmarkDescription[midPointID]["midPoint"]["Point1"]
                landmark2ID = landmarkDescription[midPointID]["midPoint"]["Point2"]
                coord = self.calculateMidPointCoord(fidList, landmark1ID, landmark2ID)
                index = fidList.GetMarkupIndexByID(midPointID)
                fidList.SetNthFiducialPositionFromArray(index, coord)
                if landmarkDescription[midPointID]["projection"]["isProjected"]:
                    hardenModel = slicer.app.mrmlScene().GetNodeByID(fidList.GetAttribute("hardenModelID"))
                    landmarkDescription[midPointID]["projection"]["closestPointIndex"] = \
                        self.projectOnSurface(hardenModel, fidList, midPointID)
                    fidList.SetAttribute("landmarkDescription",self.encodeJSON(landmarkDescription))
                self.updateMidPoint(fidList, midPointID)

    # Called when a landmarks is moved
    def onPointModifiedEvent(self, obj, event):
        print "----onPointModifiedEvent Angle plane-----"
        landmarkDescription = self.decodeJSON(obj.GetAttribute("landmarkDescription"))
        if not landmarkDescription:
            return
        selectedLandmarkID = self.findIDFromLabel(obj, self.interface.landmarkComboBox.currentText)
        # remove observer to make sure, the callback function won't work..
        tag = self.decodeJSON(obj.GetAttribute("PointModifiedEventTag"))
        obj.RemoveObserver(tag["PointModifiedEventTag"])
        if selectedLandmarkID:
            activeLandmarkState = landmarkDescription[selectedLandmarkID]
            if activeLandmarkState["projection"]["isProjected"]:
                hardenModel = slicer.app.mrmlScene().GetNodeByID(obj.GetAttribute("hardenModelID"))
                activeLandmarkState["projection"]["closestPointIndex"] = \
                    self.projectOnSurface(hardenModel, obj, selectedLandmarkID)
                obj.SetAttribute("landmarkDescription",self.encodeJSON(landmarkDescription))
            self.updateMidPoint(obj,selectedLandmarkID)
            self.findROI(obj)
        time.sleep(0.08)
        # Add the observer again
        PointModifiedEventTag = obj.AddObserver(obj.PointModifiedEvent, self.onPointModifiedEvent)
        obj.SetAttribute("PointModifiedEventTag",self.encodeJSON({"PointModifiedEventTag":PointModifiedEventTag}))

    def onMarkupRemovedEvent(self, obj, event):
        print "------markup deleting-------"
        landmarkDescription = self.decodeJSON(obj.GetAttribute("landmarkDescription"))
        IDs = []
        for ID, value in landmarkDescription.iteritems():
            isFound = False
            for n in range(obj.GetNumberOfMarkups()):
                markupID = obj.GetNthMarkupID(n)
                if ID == markupID:
                    isFound = True
            if not isFound:
                IDs.append(ID)
        for ID in IDs:
            self.deleteLandmark(obj, landmarkDescription[ID]["landmarkLabel"])
            landmarkDescription.pop(ID,None)
        obj.SetAttribute("landmarkDescription",self.encodeJSON(landmarkDescription))

    def updatePlanesEvent(self, obj, event):
        for planeControls in self.interface.planeControlsDictionary.values():
            if planeControls.fidlist is obj:
                planeControls.update()

    def addLandmarkToCombox(self, fidList, combobox, markupID):
        if not fidList:
            return
        landmarkDescription = self.decodeJSON(fidList.GetAttribute("landmarkDescription"))
        combobox.addItem(landmarkDescription[markupID]["landmarkLabel"])

    def updateAllLandmarkComboBox(self, fidList, markupID):
        # update of the Combobox that are always updated
        self.updateLandmarkComboBox(fidList, self.interface.landmarkComboBox, False)
        for planeControls in self.interface.planeControlsDictionary.values():
            if planeControls.fidlist is fidList:
                self.addLandmarkToCombox(fidList, planeControls.landmark1ComboBox, markupID)
                self.addLandmarkToCombox(fidList, planeControls.landmark2ComboBox, markupID)
                self.addLandmarkToCombox(fidList, planeControls.landmark3ComboBox, markupID)
        key = self.interface.selectPlaneForMidPoint.currentText
        plane = self.interface.planeControlsDictionary[key]
        midFidList = plane.fidlist
        if midFidList == fidList:
            self.addLandmarkToCombox(fidList, self.interface.landmarkComboBox1MidPoint, markupID)
            self.addLandmarkToCombox(fidList, self.interface.landmarkComboBox2MidPoint, markupID)

    def updateLandmarkComboBox(self, fidList, combobox, displayMidPoint = True):
        combobox.blockSignals(True)
        landmarkDescription = self.decodeJSON(fidList.GetAttribute("landmarkDescription"))
        combobox.clear()
        if not fidList:
            return
        numOfFid = fidList.GetNumberOfMarkups()
        if numOfFid > 0:
            for i in range(0, numOfFid):
                if displayMidPoint is False:
                    ID = fidList.GetNthMarkupID(i)
                    if not landmarkDescription[ID]["midPoint"]["isMidPoint"]:
                        landmarkLabel = fidList.GetNthMarkupLabel(i)
                        combobox.addItem(landmarkLabel)
                else:
                    landmarkLabel = fidList.GetNthMarkupLabel(i)
                    combobox.addItem(landmarkLabel)
        combobox.setCurrentIndex(combobox.count - 1)
        combobox.blockSignals(False)

    def deleteLandmark(self, fidList, label):
        # update of the Combobox that are always updated
        self.interface.landmarkComboBox.removeItem(self.interface.landmarkComboBox.findText(label))
        for planeControls in self.interface.planeControlsDictionary.values():
            if planeControls.fidlist is fidList:
                planeControls.landmark1ComboBox.removeItem(planeControls.landmark1ComboBox.findText(label))
                planeControls.landmark2ComboBox.removeItem(planeControls.landmark2ComboBox.findText(label))
                planeControls.landmark3ComboBox.removeItem(planeControls.landmark3ComboBox.findText(label))

    def findIDFromLabel(self, fidList, landmarkLabel):
        # find the ID of the markupsNode from the label of a landmark!
        landmarkDescription = self.decodeJSON(fidList.GetAttribute("landmarkDescription"))
        for ID, value in landmarkDescription.iteritems():
            if value["landmarkLabel"] == landmarkLabel:
                return ID
        return False

    def getClosestPointIndex(self, fidNode, inputPolyData, landmarkID):
        landmarkCoord = numpy.zeros(3)
        landmarkCoord[1] = 42
        fidNode.GetNthFiducialPosition(landmarkID, landmarkCoord)
        pointLocator = vtk.vtkPointLocator()
        pointLocator.SetDataSet(inputPolyData)
        pointLocator.AutomaticOn()
        pointLocator.BuildLocator()
        indexClosestPoint = pointLocator.FindClosestPoint(landmarkCoord)
        return indexClosestPoint

    def replaceLandmark(self, inputModelPolyData, fidNode, landmarkID, indexClosestPoint):
        landmarkCoord = [-1, -1, -1]
        inputModelPolyData.GetPoints().GetPoint(indexClosestPoint, landmarkCoord)
        fidNode.SetNthFiducialPositionFromArray(landmarkID,landmarkCoord)

    def projectOnSurface(self, modelOnProject, fidNode, selectedFidReflID):
        if selectedFidReflID:
            markupsIndex = fidNode.GetMarkupIndexByID(selectedFidReflID)
            indexClosestPoint = self.getClosestPointIndex(fidNode, modelOnProject.GetPolyData(), markupsIndex)
            self.replaceLandmark(modelOnProject.GetPolyData(), fidNode, markupsIndex, indexClosestPoint)
            return indexClosestPoint

    def calculateMidPointCoord(self, fidList, landmark1ID, landmark2ID):
        """Set the midpoint when you know the the mrml nodes"""
        landmark1Index = fidList.GetMarkupIndexByID(landmark1ID)
        landmark2Index = fidList.GetMarkupIndexByID(landmark2ID)
        coord1 = [-1, -1, -1]
        coord2 = [-1, -1, -1]
        fidList.GetNthFiducialPosition(landmark1Index, coord1)
        fidList.GetNthFiducialPosition(landmark2Index, coord2)
        midCoord = [-1, -1, -1]
        midCoord[0] = (coord1[0] + coord2[0])/2
        midCoord[1] = (coord1[1] + coord2[1])/2
        midCoord[2] = (coord1[2] + coord2[2])/2
        return midCoord

    def getMatrix(self, slice):
        self.mat = slice.GetSliceToRAS()
        # print self.mat
        # ---------------------- RED SLICE -----------------------#
        # Matrix with the elements of SliceToRAS
        m = numpy.matrix([[self.mat.GetElement(0, 0), self.mat.GetElement(0, 1), self.mat.GetElement(0, 2),
                           self.mat.GetElement(0, 3)],
                          [self.mat.GetElement(1, 0), self.mat.GetElement(1, 1), self.mat.GetElement(1, 2),
                           self.mat.GetElement(1, 3)],
                          [self.mat.GetElement(2, 0), self.mat.GetElement(2, 1), self.mat.GetElement(2, 2),
                           self.mat.GetElement(2, 3)],
                          [self.mat.GetElement(3, 0), self.mat.GetElement(3, 1), self.mat.GetElement(3, 2),
                           self.mat.GetElement(3, 3)]])
        return m

    def defineNormal(self, matrix):

        # Normal vector to the Red slice:
        n_vector = numpy.matrix([[0], [0], [1], [1]])

        # point on the Red slice:
        A = numpy.matrix([[0], [0], [0], [1]])

        normalVector = matrix * n_vector
        # print "n : \n", normalVector
        A = matrix * A

        normalVector1 = normalVector

        normalVector1[0] = normalVector[0] - A[0]
        normalVector1[1] = normalVector[1] - A[1]
        normalVector1[2] = normalVector[2] - A[2]

        #print normalVector1

        return normalVector1

    def getAngle(self, normalVect1, normalVect2):

        norm1 = sqrt(
            normalVect1[0] * normalVect1[0] + normalVect1[1] * normalVect1[1] + normalVect1[2] * normalVect1[2])
        # print "norme 1: \n", norm1
        norm2 = sqrt(
            normalVect2[0] * normalVect2[0] + normalVect2[1] * normalVect2[1] + normalVect2[2] * normalVect2[2])
        #print "norme 2: \n", norm2


        scalar_product = (
            normalVect1[0] * normalVect2[0] + normalVect1[1] * normalVect2[1] + normalVect1[2] * normalVect2[2])
        #print "scalar product : \n", scalar_product

        angle = acos(scalar_product / (norm1 * norm2))

        #print "radian angle : ", angle

        angle_degree = angle * 180 / pi
        #print "Angle in degree", angle_degree


        norm1_RL = sqrt(normalVect1[1] * normalVect1[1] + normalVect1[2] * normalVect1[2])
        #print "norme RL: \n", norm1_RL
        norm2_RL = sqrt(normalVect2[1] * normalVect2[1] + normalVect2[2] * normalVect2[2])
        #print "norme RL: \n", norm2_RL

        if (norm1_RL == 0 or norm2_RL == 0):
            self.angle_degre_RL = 0
            self.angle_degre_RL_comp = 0
        else:
            scalar_product_RL = (normalVect1[1] * normalVect2[1] + normalVect1[2] * normalVect2[2])
            #print "scalar product : \n", scalar_product_RL
            inter = scalar_product_RL / (norm1_RL * norm2_RL)
            if inter >= [[ 0.99999]]:
                angleRL = 0
            else:
                angleRL = acos(inter)
            #print "radian angle : ", angleRL

            self.angle_degre_RL = angleRL * 180 / pi
            self.angle_degre_RL = round(self.angle_degre_RL, 2)
            #print self.angle_degre_RL
            self.angle_degre_RL_comp = 180 - self.angle_degre_RL

        norm1_SI = sqrt(normalVect1[0] * normalVect1[0] + normalVect1[1] * normalVect1[1])
        #print "norme1_SI : \n", norm1_SI
        norm2_SI = sqrt(normalVect2[0] * normalVect2[0] + normalVect2[1] * normalVect2[1])
        #print "norme2_SI : \n", norm2_SI

        if (norm1_SI == 0 or norm2_SI == 0):
            self.angle_degre_SI = 0
            self.angle_degre_SI_comp = 0
        else:
            scalar_product_SI = (normalVect1[0] * normalVect2[0] + normalVect1[1] * normalVect2[1])
            #print "scalar product_SI : \n", scalar_product_SI

            inter = scalar_product_SI / (norm1_SI * norm2_SI)
            if inter >= [[ 0.99999]]:
                angleSI = 0
            else:
                angleSI = acos(inter)
            #print "radian angle : ", angleSI

            self.angle_degre_SI = angleSI * 180 / pi
            self.angle_degre_SI = round(self.angle_degre_SI, 2)
            #print self.angle_degre_SI
            self.angle_degre_SI_comp = 180 - self.angle_degre_SI
            #print self.angle_degre_SI_comp

        norm1_AP = sqrt(normalVect1[0] * normalVect1[0] + normalVect1[2] * normalVect1[2])
        #print "norme1_SI : \n", norm1_AP
        norm2_AP = sqrt(normalVect2[0] * normalVect2[0] + normalVect2[2] * normalVect2[2])
        #print "norme2_SI : \n", norm2_AP

        if (norm1_AP == 0 or norm2_AP == 0):
            self.angle_degre_AP = 0
            self.angle_degre_AP_comp = 0
        else:
            scalar_product_AP = (normalVect1[0] * normalVect2[0] + normalVect1[2] * normalVect2[2])
            #print "scalar product_SI : \n", scalar_product_AP

            #print "VALUE :", scalar_product_AP/(norm1_AP*norm2_AP)
            inter = scalar_product_AP / (norm1_AP * norm2_AP)
            if inter >= [[ 0.99999]]:
                angleAP = 0
            else:
                angleAP = acos(inter)

            #print "radian angle : ", angleAP

            self.angle_degre_AP = angleAP * 180 / pi
            self.angle_degre_AP = round(self.angle_degre_AP, 2)
            #print self.angle_degre_AP
            self.angle_degre_AP_comp = 180 - self.angle_degre_AP

    def normalLandmarks(self, GA, GB):
        Vn = numpy.matrix([[0], [0], [0]])
        Vn[0] = GA[1] * GB[2] - GA[2] * GB[1]
        Vn[1] = GA[2] * GB[0] - GA[0] * GB[2]
        Vn[2] = GA[0] * GB[1] - GA[1] * GB[0]

        #print "Vn = ",Vn

        norm_Vn = sqrt(Vn[0] * Vn[0] + Vn[1] * Vn[1] + Vn[2] * Vn[2])

        #print "norm_Vn = ",norm_Vn

        Normal = Vn / norm_Vn

        #print "N = ",Normal

        return Normal

    def planeLandmarks(self, fidList, Landmark1Label, Landmark2Label, Landmark3Label,
                       AdaptToBoundingBoxCheckBox, sliderOpacity, planeCollection, actor):
        # Limit the number of 3 landmarks to define a plane
        # Keep the coordinates of the landmarks
        landmark1ID = self.findIDFromLabel(fidList, Landmark1Label)
        landmark2ID = self.findIDFromLabel(fidList, Landmark2Label)
        landmark3ID = self.findIDFromLabel(fidList, Landmark3Label)

        if not (landmark1ID and landmark2ID and landmark3ID):
            print "landmark not defined"
            return

        if AdaptToBoundingBoxCheckBox.isChecked():
            slider = 10000
        else:
            slider = 1

        coord = numpy.zeros(3)
        landmark1Index = fidList.GetMarkupIndexByID(landmark1ID)
        fidList.GetNthFiducialPosition(landmark1Index, coord)
        #print "Landmark1Value: ", coord
        r1 = coord[0]
        a1 = coord[1]
        s1 = coord[2]
        landmark2Index = fidList.GetMarkupIndexByID(landmark2ID)
        fidList.GetNthFiducialPosition(landmark2Index, coord)
        #print "Landmark2Value: ", coord
        r2 = coord[0]
        a2 = coord[1]
        s2 = coord[2]
        landmark3Index = fidList.GetMarkupIndexByID(landmark3ID)
        fidList.GetNthFiducialPosition(landmark3Index, coord)
        #print "Landmark3Value: ", coord
        r3 = coord[0]
        a3 = coord[1]
        s3 = coord[2]

        points = vtk.vtkPoints()
        if points.GetNumberOfPoints() == 0:
            points.InsertNextPoint(r1, a1, s1)
            points.InsertNextPoint(r2, a2, s2)
            points.InsertNextPoint(r3, a3, s3)
        else:
            points.SetPoint(0, r1, a1, s1)
            points.SetPoint(1, r2, a2, s2)
            points.SetPoint(2, r3, a3, s3)
        #print "points ", points

        polydata = vtk.vtkPolyData()
        polydata.SetPoints(points)

        centerOfMass = vtk.vtkCenterOfMass()
        centerOfMass.SetInputData(polydata)
        centerOfMass.SetUseScalarsAsWeights(False)
        centerOfMass.Update()

        G = centerOfMass.GetCenter()

        #print "Center of mass = ",G

        A = (r1, a1, s1)
        B = (r2, a2, s2)
        C = (r3, a3, s3)

        # Vector GA
        GA = numpy.matrix([[0.0], [0.0], [0.0]])
        GA[0] = A[0] - G[0]
        GA[1] = A[1] - G[1]
        GA[2] = A[2] - G[2]

        #print "GA = ", GA

        # Vector BG
        GB = numpy.matrix([[0.0], [0.0], [0.0]])
        GB[0] = B[0] - G[0]
        GB[1] = B[1] - G[1]
        GB[2] = B[2] - G[2]

        #print "GB = ", GB

        # Vector CG
        GC = numpy.matrix([[0.0], [0.0], [0.0]])
        GC[0] = C[0] - G[0]
        GC[1] = C[1] - G[1]
        GC[2] = C[2] - G[2]

        #print "GC = ", GC

        self.N = self.normalLandmarks(GA, GB)

        D = numpy.matrix([[0.0], [0.0], [0.0]])
        E = numpy.matrix([[0.0], [0.0], [0.0]])
        F = numpy.matrix([[0.0], [0.0], [0.0]])

        D[0] = slider * GA[0] + G[0]
        D[1] = slider * GA[1] + G[1]
        D[2] = slider * GA[2] + G[2]

        #print "Slider value : ", slider

        #print "D = ",D

        E[0] = slider * GB[0] + G[0]
        E[1] = slider * GB[1] + G[1]
        E[2] = slider * GB[2] + G[2]

        #print "E = ",E

        F[0] = slider * GC[0] + G[0]
        F[1] = slider * GC[1] + G[1]
        F[2] = slider * GC[2] + G[2]

        #print "F = ",F

        planeSource = vtk.vtkPlaneSource()
        planeSource.SetNormal(self.N[0], self.N[1], self.N[2])

        planeSource.SetOrigin(D[0], D[1], D[2])
        planeSource.SetPoint1(E[0], E[1], E[2])
        planeSource.SetPoint2(F[0], F[1], F[2])

        planeSource.Update()

        if AdaptToBoundingBoxCheckBox.isChecked():
            clipper = vtk.vtkClipClosedSurface()
            clipper.SetClippingPlanes(planeCollection)
            clipper.SetInputData(planeSource.GetOutput())
            clipper.Update()
            plane = clipper.GetOutput()
        else:
            plane = planeSource.GetOutput()

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(plane)
        mapper.Update()

        actor.SetMapper(mapper)
        actor.GetProperty().SetColor(0, 0.4, 0.8)
        actor.GetProperty().SetOpacity(sliderOpacity)

        renderer = list()
        renderWindow = list()
        layoutManager = slicer.app.layoutManager()
        for i in range(0, layoutManager.threeDViewCount):
            threeDWidget = layoutManager.threeDWidget(i)
            threeDView = threeDWidget.threeDView()
            renderWindow.append(threeDView.renderWindow())
            renderers = renderWindow[i].GetRenderers()
            renderer.append(renderers.GetFirstRenderer())
            renderer[i].AddViewProp(actor)
            renderWindow[i].AddRenderer(renderer[i])
            renderer[i].Render()
            renderWindow[i].Render()

    def GetConnectedVertices(self, connectedVerticesIDList, polyData, pointID):
        # Return IDs of all the vertices that compose the first neighbor.
        cellList = vtk.vtkIdList()
        connectedVerticesIDList.InsertUniqueId(pointID)
        # Get cells that vertex 'pointID' belongs to
        polyData.GetPointCells(pointID, cellList)
        numberOfIds = cellList.GetNumberOfIds()
        for i in range(0, numberOfIds):
            # Get points which compose all cells
            pointIdList = vtk.vtkIdList()
            polyData.GetCellPoints(cellList.GetId(i), pointIdList)
            for j in range(0, pointIdList.GetNumberOfIds()):
                connectedVerticesIDList.InsertUniqueId(pointIdList.GetId(j))
        return connectedVerticesIDList

    def addArrayFromIdList(self, connectedIdList, inputModelNode, arrayName):
        if not inputModelNode:
            return
        inputModelNodePolydata = inputModelNode.GetPolyData()
        pointData = inputModelNodePolydata.GetPointData()
        numberofIds = connectedIdList.GetNumberOfIds()
        hasArrayInt = pointData.HasArray(arrayName)
        if hasArrayInt == 1:  # ROI Array found
            pointData.RemoveArray(arrayName)
        arrayToAdd = vtk.vtkDoubleArray()
        arrayToAdd.SetName(arrayName)
        for i in range(0, inputModelNodePolydata.GetNumberOfPoints()):
            arrayToAdd.InsertNextValue(0.0)
        for i in range(0, numberofIds):
            arrayToAdd.SetValue(connectedIdList.GetId(i), 1.0)
        lut = vtk.vtkLookupTable()
        tableSize = 2
        lut.SetNumberOfTableValues(tableSize)
        lut.Build()
        displayNode = inputModelNode.GetDisplayNode()
        rgb = displayNode.GetColor()
        lut.SetTableValue(0, rgb[0], rgb[1], rgb[2], 1)
        lut.SetTableValue(1, 1.0, 0.0, 0.0, 1)
        arrayToAdd.SetLookupTable(lut)
        pointData.AddArray(arrayToAdd)
        inputModelNodePolydata.Modified()
        return True

    def displayROI(self, inputModelNode, scalarName):
        PolyData = inputModelNode.GetPolyData()
        PolyData.Modified()
        displayNode = inputModelNode.GetModelDisplayNode()
        displayNode.SetScalarVisibility(False)
        disabledModify = displayNode.StartModify()
        displayNode.SetActiveScalarName(scalarName)
        displayNode.SetScalarVisibility(True)
        displayNode.EndModify(disabledModify)

    def findROI(self, fidList):
        hardenModel = slicer.app.mrmlScene().GetNodeByID(fidList.GetAttribute("hardenModelID"))
        connectedModel = slicer.app.mrmlScene().GetNodeByID(fidList.GetAttribute("connectedModelID"))
        landmarkDescription = self.decodeJSON(fidList.GetAttribute("landmarkDescription"))
        arrayName = fidList.GetAttribute("arrayName")
        ROIPointListID = vtk.vtkIdList()
        for key,activeLandmarkState in landmarkDescription.iteritems():
            tempROIPointListID = vtk.vtkIdList()
            if activeLandmarkState["ROIradius"] != 0:
                self.defineNeighbor(tempROIPointListID,
                                    hardenModel.GetPolyData(),
                                    activeLandmarkState["projection"]["closestPointIndex"],
                                    activeLandmarkState["ROIradius"])
            for j in range(0, tempROIPointListID.GetNumberOfIds()):
                ROIPointListID.InsertUniqueId(tempROIPointListID.GetId(j))
        listID = ROIPointListID
        self.addArrayFromIdList(listID, connectedModel, arrayName)
        self.displayROI(connectedModel, arrayName)
        return ROIPointListID

    def warningMessage(self, message):
        messageBox = ctk.ctkMessageBox()
        messageBox.setWindowTitle(" /!\ WARNING /!\ ")
        messageBox.setIcon(messageBox.Warning)
        messageBox.setText(message)
        messageBox.setStandardButtons(messageBox.Ok)
        messageBox.exec_()

    def encodeJSON(self, input):
        encodedString = json.dumps(input)
        encodedString = encodedString.replace('\"', '\'')
        return encodedString

    def decodeJSON(self, input):
        input = input.replace('\'','\"')
        return self.byteify(json.loads(input))

    def byteify(self, input):
        if isinstance(input, dict):
            return {self.byteify(key):self.byteify(value) for key,value in input.iteritems()}
        elif isinstance(input, list):
            return [self.byteify(element) for element in input]
        elif isinstance(input, unicode):
            return input.encode('utf-8')
        else:
            return input

class AnglePlanesTest(ScriptedLoadableModuleTest):
    def setUp(self):
        # reset the state - clear scene
        slicer.mrmlScene.Clear(0)

    def runTest(self):
        # run all tests needed
        self.delayDisplay("Clear the scene")
        self.setUp()
        self.delayDisplay("Download and load datas")
        self.downloaddata()
        self.delayDisplay("Starting the tests")
        self.assertTrue(self.test_AnglePlanes())
        self.delayDisplay('All tests passed!')

    def downloaddata(self):
        import urllib
        downloads = (
            ('http://slicer.kitware.com/midas3/download?items=213632', '01.vtk', slicer.util.loadModel),
            ('http://slicer.kitware.com/midas3/download?items=213633', '02.vtk', slicer.util.loadModel),
        )
        for url, name, loader in downloads:
            filePath = slicer.app.temporaryPath + '/' + name
            print filePath
            if not os.path.exists(filePath) or os.stat(filePath).st_size == 0:
                logging.info('Requesting download %s from %s...\n' % (name, url))
                urllib.urlretrieve(url, filePath)
            if loader:
                logging.info('Loading %s...' % (name,))
                loader(filePath)

        layoutManager = slicer.app.layoutManager()
        threeDWidget = layoutManager.threeDWidget(0)
        threeDView = threeDWidget.threeDView()
        threeDView.resetFocalPoint()

    def test_AnglePlanes(self):

        widget = slicer.modules.AnglePlanesWidget

        self.delayDisplay('Saving planes')
        widget.savePlanes("test.p")

        self.delayDisplay('Loading planes')
        widget.readPlanes("test.p")

        self.delayDisplay('Adding planes')

        widget.inputModelSelector.setCurrentNode(
            slicer.mrmlScene.GetNodesByName("01").GetItemAsObject(0))
        movingMarkupsFiducial = slicer.vtkMRMLMarkupsFiducialNode()
        movingMarkupsFiducial.SetName("F1")
        slicer.mrmlScene.AddNode(movingMarkupsFiducial)
        widget.inputLandmarksSelector.setCurrentNode(movingMarkupsFiducial)
        widget.addNewPlane()
        plane1 = widget.planeControlsDictionary["Plane 1"]
        movingMarkupsFiducial.AddFiducial(8.08220491, -98.03022892, 93.12060543)
        widget.logic.onPointModifiedEvent(movingMarkupsFiducial,None)
        movingMarkupsFiducial.AddFiducial(-64.97482242, -26.20270453, 40.0195569)
        widget.logic.onPointModifiedEvent(movingMarkupsFiducial,None)
        movingMarkupsFiducial.AddFiducial(-81.14900734, -108.26332837, 121.16330592)
        widget.logic.onPointModifiedEvent(movingMarkupsFiducial,None)
        plane1.landmark1ComboBox.setCurrentIndex(0)
        plane1.landmark2ComboBox.setCurrentIndex(1)
        plane1.landmark3ComboBox.setCurrentIndex(2)

        widget.inputModelSelector.setCurrentNode(
            slicer.mrmlScene.GetNodesByName("02").GetItemAsObject(0))
        movingMarkupsFiducial = slicer.vtkMRMLMarkupsFiducialNode()
        movingMarkupsFiducial.SetName("F2")
        slicer.mrmlScene.AddNode(movingMarkupsFiducial)
        widget.inputLandmarksSelector.setCurrentNode(movingMarkupsFiducial)
        widget.addNewPlane()
        plane2 = widget.planeControlsDictionary["Plane 2"]
        movingMarkupsFiducial.AddFiducial(-39.70435272, -97.08191652, 91.88711809)
        widget.logic.onPointModifiedEvent(movingMarkupsFiducial,None)
        movingMarkupsFiducial.AddFiducial(-96.02709079, -18.26063616, 21.47774342)
        widget.logic.onPointModifiedEvent(movingMarkupsFiducial,None)
        movingMarkupsFiducial.AddFiducial(-127.93278815, -106.45001448, 92.35628815)
        widget.logic.onPointModifiedEvent(movingMarkupsFiducial,None)
        plane2.landmark1ComboBox.setCurrentIndex(0)
        plane2.landmark2ComboBox.setCurrentIndex(1)
        plane2.landmark3ComboBox.setCurrentIndex(2)

        self.delayDisplay('Hide Planes')
        plane1.HidePlaneCheckBox.setChecked(True)
        plane2.HidePlaneCheckBox.setChecked(True)

        self.delayDisplay('Adapt on bounding box')
        plane1.HidePlaneCheckBox.setChecked(False)
        plane2.HidePlaneCheckBox.setChecked(False)
        plane1.AdaptToBoundingBoxCheckBox.setChecked(True)
        plane2.AdaptToBoundingBoxCheckBox.setChecked(True)

        self.delayDisplay('Selecting planes')
        widget.planeComboBox1.setCurrentIndex(4)
        widget.planeComboBox2.setCurrentIndex(4)

        self.delayDisplay('Calculating angle')
        widget.angleValue()

        test = widget.logic.angle_degre_RL != 59.06 or widget.logic.angle_degre_RL_comp != 120.94 or widget.logic.angle_degre_SI != 12.53 or widget.logic.angle_degre_SI_comp != 167.47 or widget.logic.angle_degre_AP != 82.56 or widget.logic.angle_degre_AP_comp != 97.44

        self.delayDisplay('Testing angles')
        if test:

            print "", "Angle", "Complementary"
            print "R-L-View", widget.logic.angle_degre_RL, widget.logic.angle_degre_RL_comp
            print "S-I-View", widget.logic.angle_degre_SI, widget.logic.angle_degre_SI_comp
            print "A-P-View", widget.logic.angle_degre_AP, widget.logic.angle_degre_AP_comp
            self.delayDisplay('Test Failure!')

        else:
            self.delayDisplay('Test passed!')
