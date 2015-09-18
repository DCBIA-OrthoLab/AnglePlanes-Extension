from __main__ import vtk, qt, ctk, slicer

import numpy
import copy
from math import *

from slicer.ScriptedLoadableModule import *

import os
import pickle
import time

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
            self.anglePlanes.removeModelPointLocator(callData.GetName())
            self.anglePlanes.updateOnSurfaceCheckBoxes()
        if isinstance(callData, slicer.vtkMRMLMarkupsFiducialNode):
            name = callData.GetName()
            planeid = name[len('P'):]
            name = "Plane " + planeid
            if name in self.anglePlanes.planeControlsDictionary.keys():
                self.anglePlanes.RemoveManualPlane(planeid)

    def onModelNodePolyDataModified(self, caller, eventId):
        self.anglePlanes.addModelPointLocator(caller.GetName(), caller.GetPolyData())

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
        parent.contributors = ["Julia Lopinto", "Juan Carlos Prieto", "Francois Budin"]
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
        #self.midPointFiducialDictionaryID = {}
        # self.logic.initializePlane()
        self.ignoredNodeNames = ('Red Volume Slice', 'Yellow Volume Slice', 'Green Volume Slice')

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

        self.CollapsibleButton = ctk.ctkCollapsibleButton()
        self.CollapsibleButton.text = "Manage planes"
        self.layout.addWidget(self.CollapsibleButton)
        self.managePlanesFormLayout = qt.QFormLayout(self.CollapsibleButton)
        self.CollapsibleButton.checked = True

        # Add planes and manage landmark addition to each plane

        addNewPlaneLayout = qt.QHBoxLayout()
        addPlaneLabel = qt.QLabel('Add new plane')
        self.addPlaneButton = qt.QPushButton(qt.QIcon(":/Icons/MarkupsAddFiducial.png"), " ")
        self.addPlaneButton.setFixedSize(50, 25)
        self.addPlaneButton.connect('clicked()', self.addNewPlane)
        self.addPlaneButton.setEnabled(True)
        addNewPlaneLayout.addWidget(addPlaneLabel)
        addNewPlaneLayout.addWidget(self.addPlaneButton)

        self.managePlanesFormLayout.addRow(addNewPlaneLayout)

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
        self.defineRemoveMiddlePointButton = qt.QPushButton(' Remove middle point ')
        middlePointLayout = qt.QHBoxLayout()
        middlePointLayout.addWidget(self.defineMiddlePointButton)
        middlePointLayout.addWidget(self.defineRemoveMiddlePointButton)
        middlePointLayout.addWidget(self.midPointOnSurfaceCheckBox)
        landmark1Layout.addRow(middlePointLayout)
        self.midPointGroupBox.setLayout(landmark1Layout)
        self.midPointGroupBox.setDisabled(True)
        self.defineMiddlePointButton.connect('clicked()', self.onAddMidPoint)
        self.defineRemoveMiddlePointButton.connect('clicked()', self.onRemoveMidPoint)
        self.landmarkComboBox1MidPoint.connect('currentIndexChanged(int)', self.onUpdateMidPoint)
        self.landmarkComboBox2MidPoint.connect('currentIndexChanged(int)', self.onUpdateMidPoint)
        self.midPointOnSurfaceCheckBox.connect('stateChanged(int)', self.onSurfaceMidPointStateChanged)

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
        # Setting combo boxes at different values/index otherwise infinite loop
        self.planeComboBox1.setCurrentIndex(0)
        self.planeComboBox2.setCurrentIndex(1)
        self.valueComboBox()

        save.connect('clicked(bool)', self.onSavePlanes)
        read.connect('clicked(bool)', self.onReadPlanes)

        slicer.mrmlScene.AddObserver(slicer.mrmlScene.EndCloseEvent, self.onCloseScene)

        self.pointLocatorDictionary = {}

        for i in self.getPositionOfModelNodes(False):
            modelnode = slicer.mrmlScene.GetNthNodeByClass(i, "vtkMRMLModelNode")
            self.addModelPointLocator(modelnode.GetName(), modelnode.GetPolyData())
            modelnode.AddObserver(modelnode.DisplayModifiedEvent, self.onChangeModelDisplay)
        self.middleFiducialDictionary = dict()
        ModelAddedClass(self)
        self.onUpdateMidPoint()

    def canAddMiddlePoint(self):
        if self.landmarkComboBox1MidPoint.currentText == self.landmarkComboBox2MidPoint.currentText\
                or self.landmarkComboBox1MidPoint.count == 0 or self.landmarkComboBox2MidPoint.count == 0:
            return False
        else:
            return True

    def onUpdateMidPoint(self, remove=False):
        if self.currentMidPointExists(remove):
            self.defineRemoveMiddlePointButton.setDisabled(False)
            self.defineMiddlePointButton.setDisabled(True)
        else:
            self.defineRemoveMiddlePointButton.setDisabled(True)
            self.defineMiddlePointButton.setDisabled(False)
        disableMiddlePointSurfaceCheckbox = False
        if not self.canAddMiddlePoint():
            self.defineMiddlePointButton.setDisabled(True)
        self.updateOnSurfaceCheckBoxes()

    def onSurfaceMidPointStateChanged(self):
        key = self.getCurrentMidPointFiducialStructure()
        if key != '':
            self.middleFiducialDictionary[key].onSurface = self.midPointOnSurfaceCheckBox.isChecked()
            if self.selectPlaneForMidPoint.currentText in self.planeControlsDictionary.keys():
                self.planeControlsDictionary[self.selectPlaneForMidPoint.currentText].update()

    def onChangeMiddlePointFiducialNode(self):
        for x in [self.landmarkComboBox1MidPoint, self.landmarkComboBox2MidPoint]:
            current = x.currentText
            x.clear()
            node = self.selectedMiddlePointPlane()
            if not node:
                return
            for i in range(0, node.GetNumberOfMarkups()):
                x.addItem(node.GetNthFiducialLabel(i))
            if x.findText(current) > -1:
                x.setCurrentIndex(x.findText(current))

    def onChangeModelDisplay(self, obj, event):
        self.updateOnSurfaceCheckBoxes()

    def fillColorsComboBox(self, planeComboBox):
        planeComboBox.clear()
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
        # if they are new models and if they are visible, allow to select "on surface" to place new fiducials
        if numberOfVisibleModels > 0:
            if self.currentMidPointExists():
                key = self.getCurrentMidPointFiducialStructure()
                self.midPointOnSurfaceCheckBox.setDisabled(False)
                self.midPointOnSurfaceCheckBox.setChecked(self.middleFiducialDictionary[key].onSurface)
            else:
                self.midPointOnSurfaceCheckBox.setChecked(False)
                self.midPointOnSurfaceCheckBox.setDisabled(True)
            for x in self.planeControlsDictionary.values():
                x.surfaceDeplacementCheckBox.setDisabled(False)
        # else there are no visible models or if they are not visible, disable "on surface" to place new fiducials
        else:
            self.midPointOnSurfaceCheckBox.setDisabled(True)
            self.midPointOnSurfaceCheckBox.setChecked(False)
            for x in self.planeControlsDictionary.values():
                x.surfaceDeplacementCheckBox.setChecked(False)
                x.surfaceDeplacementCheckBox.setDisabled(True)

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

    def enter(self):
        if self.autoChangeLayout.isChecked():
            lm = slicer.app.layoutManager()
            self.currentLayout = lm.layout
            lm.setLayout(4)  # 3D-View

    def exit(self):
        if self.autoChangeLayout.isChecked():
            lm = slicer.app.layoutManager()
            if lm.layout == 4:  # the user has not manually changed the layout
                lm.setLayout(self.currentLayout)

    def removeModelPointLocator(self, name):
        if name in self.pointLocatorDictionary:
            print("Removing point locator {0}".format(name))
            del self.pointLocatorDictionary[name]

    def addModelPointLocator(self, name, polydata):

        if name not in self.pointLocatorDictionary and name not in self.ignoredNodeNames:
            print "Adding point locator: {0}".format(name)
            pointLocator = vtk.vtkPointLocator()
            pointLocator.SetDataSet(polydata)
            pointLocator.AutomaticOn()
            pointLocator.BuildLocator()

            self.pointLocatorDictionary[name] = pointLocator

    def addNewPlane(self, keyLoad=-1):
        if keyLoad != -1:
            self.planeControlsId = keyLoad
        else:
            self.planeControlsId += 1
        if len(self.planeControlsDictionary) >= 1:
            self.addPlaneButton.setDisabled(True)
        planeControls = AnglePlanesWidgetPlaneControl(self, self.planeControlsId, self.pointLocatorDictionary)
        self.managePlanesFormLayout.addRow(planeControls)

        key = "Plane " + str(self.planeControlsId)
        self.planeControlsDictionary[key] = planeControls
        self.updatePlanesComboBoxes()
        self.midPointGroupBox.setDisabled(False)
        self.selectPlaneForMidPoint.addItem(key)


    def RemoveManualPlane(self, id):
        key = "Plane " + str(id)
        # If the plane has already been removed (for example, when removing this plane in this function,
        # the callback on removing the nodes will be called, and therefore this function will be called again
        # We need to not do anything the second time this function is called for the same plane
        if key not in self.planeControlsDictionary.keys():
            return
        fiducialList = slicer.util.getNode('P' + str(id))
        planeControls = self.planeControlsDictionary[key]
        self.managePlanesFormLayout.removeWidget(planeControls)
        self.planeControlsDictionary[key].deleteLater()
        self.planeControlsDictionary.pop(key)
        self.addPlaneButton.setDisabled(False)
        if len(self.planeControlsDictionary.keys()) == 0:
            self.midPointGroupBox.setDisabled(True)
            self.midPointGroupBox.collapsed = True
        self.updatePlanesComboBoxes()
        self.valueComboBox()
        if self.selectPlaneForMidPoint.findText(key) > -1:
            self.selectPlaneForMidPoint.removeItem(self.selectPlaneForMidPoint.findText(key))
        if fiducialList:
            # fiducialList.SetDisplayVisibility(False)
            fiducialList.RemoveObserver(fiducialList.onFiducialAddedObserverTag)
            fiducialList.RemoveObserver(fiducialList.onFiducialRemovedObserverTag)
            fiducialList.RemoveObserver(fiducialList.setPointModifiedEventObserverTag)
            fiducialList.RemoveObserver(fiducialList.onFiducialAddedMidPointObserverTag)
            fiducialList.RemoveObserver(fiducialList.onFiducialRemovedMidPointObserverTag)
            if planeControls.removeFiducials.checkState() == qt.Qt.Checked:
                slicer.app.mrmlScene().RemoveNode(fiducialList)

    def onComputeBox(self):
        positionOfVisibleNodes = self.getPositionOfModelNodes(True)
        if len(positionOfVisibleNodes) == 0:
            return
        maxValue = slicer.sys.float_info.max
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

        def CreateNewNode(colorName, color, dim, origin):
            # we add a pseudo-random number to the name of our empty volume to avoid the risk of having a volume called
            #  exactly the same by the user which could be confusing. We could also have used slicer.app.sessionId()
            VolumeName = "AnglePlanes_EmptyVolume_" + str(slicer.app.applicationPid()) + "_" + colorName
            sampleVolumeNode = slicer.util.getNode(VolumeName)
            if sampleVolumeNode == None:
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
                print "first"
            sampleVolumeNode.SetOrigin(origin[0], origin[1], origin[2])
            sampleVolumeNode.SetSpacing(dim[0], dim[1], dim[2])
            if not hasattr(slicer, 'vtkMRMLLabelMapVolumeNode'):
                sampleVolumeNode.SetLabelMap(1)
            sampleVolumeNode.SetHideFromEditors(True)
            sampleVolumeNode.SetSaveWithScene(False)
            return sampleVolumeNode

        dictColors = {'Red': 32, 'Yellow': 15, 'Green': 1}
        for x in dictColors.keys():
            sampleVolumeNode = CreateNewNode(x, dictColors[x], dim, origin)
            compNode = slicer.util.getNode('vtkMRMLSliceCompositeNode' + x)
            compNode.SetLinkedControl(False)
            compNode.SetBackgroundVolumeID(sampleVolumeNode.GetID())
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

    def selectedMiddlePointPlane(self):
        if self.selectPlaneForMidPoint.currentText not in self.planeControlsDictionary.keys():
            return None
        id = self.planeControlsDictionary[self.selectPlaneForMidPoint.currentText].id
        markupNodeName = 'P' + str(id)
        nodes = slicer.mrmlScene.GetNodesByClassByName('vtkMRMLMarkupsFiducialNode', markupNodeName)
        node = nodes.GetItemAsObject(0)
        return node

    def computeMidPointPosition(self, node, p1ID, p2ID, coord):
        f = list()
        f.append(type('obj', (object,), {'ID': p1ID, 'coordinates': numpy.zeros(3)}))
        f.append(type('obj', (object,), {'ID': p2ID, 'coordinates': numpy.zeros(3)}))

        if not node:
            return 1
        found = 0
        for j in (0,1):
            fid = node.GetMarkupIndexByID(f[j].ID)
            if fid != -1:
                current = numpy.zeros(3)
                node.GetNthFiducialPosition(fid, current)
                f[j].coordinates = current
                found += 1
        if not found == 2:
            print "Error: Fiducials not found in lists"
            return 1
        current = f[0].coordinates + f[1].coordinates
        current /= 2
        for i in range(0,3):
            coord[i] = current[i]
        return 0

    def getFiducialIDFromName(self, node, name):
        for i in range(0, node.GetNumberOfMarkups()):
            if name == node.GetNthFiducialLabel(i):
                return node.GetNthMarkupID(i)
        return ''

    def onAddMidPoint(self):
        if self.currentMidPointExists():
            print "Mid point already exists"
            return
        node = self.selectedMiddlePointPlane()
        f = list()
        f.append(type('obj', (object,), {'name': self.landmarkComboBox1MidPoint.currentText, 'ID': ""}))
        f.append(type('obj', (object,), {'name': self.landmarkComboBox2MidPoint.currentText, 'ID': ""}))
        for j in (0,1):
            f[j].ID = self.getFiducialIDFromName(node, f[j].name)
        if '' in [f[0].ID, f[1].ID]:
            print "Error: Fiducials not found in lists"
            return
        coordinates = numpy.zeros(3)
        self.computeMidPointPosition(node, f[0].ID, f[1].ID, coordinates)
        node.AddFiducial(coordinates[0], coordinates[1], coordinates[2], f[0].name+"-"+f[1].name+"-mid-pt")
        newFiducial = node.GetNumberOfMarkups() - 1
        node.SetNthFiducialSelected(newFiducial, False)
        node.SetNthMarkupLocked(newFiducial, True)
        middleFiducial = AnglePlanesMiddleFiducial(f[0].ID, f[1].ID, self.midPointOnSurfaceCheckBox.isChecked(), node.GetID())
        self.middleFiducialDictionary[node.GetNthMarkupID(newFiducial)] = middleFiducial
        self.onUpdateMidPoint()

    def currentMidPointExists(self, remove=False):
        for x in self.middleFiducialDictionary.keys():
            node = self.selectedMiddlePointPlane()
            middleFiducial = self.middleFiducialDictionary[x]
            if node.GetID() == middleFiducial.nodeID:
                P1 = middleFiducial.P1
                P2 = middleFiducial.P2
                L1 = self.getFiducialIDFromName(node, self.landmarkComboBox1MidPoint.currentText)
                L2 = self.getFiducialIDFromName(node, self.landmarkComboBox2MidPoint.currentText)
                if P1 == L1 and P2 == L2 or P1 == L2 and P2 == L1:
                    if remove is True:
                        node.RemoveMarkup(node.GetMarkupIndexByID(x))
                        return False
                    else:
                        return True
        return False

    def getCurrentMidPointFiducialStructure(self):
        if self.currentMidPointExists():
            for x in self.middleFiducialDictionary.keys():
                node = self.selectedMiddlePointPlane()
                middleFiducial = self.middleFiducialDictionary[x]
                if node.GetID() == middleFiducial.nodeID:
                    P1 = middleFiducial.P1
                    P2 = middleFiducial.P2
                    L1 = self.getFiducialIDFromName(node, self.landmarkComboBox1MidPoint.currentText)
                    L2 = self.getFiducialIDFromName(node, self.landmarkComboBox2MidPoint.currentText)
                    if P1 == L1 and P2 == L2 or P1 == L2 and P2 == L1:
                        return x
        return ''

    def onRemoveMidPoint(self):
        self.onUpdateMidPoint(True)

    def onFiducialChangedMidPoint(self, obj, event):
        fidlist = obj
        node = self.selectedMiddlePointPlane()
        if not node or not fidlist == node:
            return
        self.onChangeMiddlePointFiducialNode()

    def fiducialInList(self, name, fidlist):
        for i in range(0, fidlist.GetNumberOfFiducials()):
            if name == fidlist.GetNthFiducialLabel(i):
                return True
        return False

    def onCloseScene(self, obj, event):
        self.middleFiducialDictionary = dict()
        keys = self.planeControlsDictionary.keys()
        for x in keys[len('Plane '):]:
            self.RemoveManualPlane(x)
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
            allItems = [comboBox.itemText(i) for i in range(comboBox.count)]
            for i in allItems:
                if i != noThisString:
                    comboBox.setCurrentIndex(comboBox.findText(i))
                    break
        else:
            comboBox.setCurrentIndex(comboBox.findText(oldString))


    def updatePlanesComboBoxes(self):
        self.planeComboBox1.blockSignals(True)
        self.planeComboBox2.blockSignals(True)
        colorPlane1 = self.planeComboBox1.currentText
        colorPlane2 = self.planeComboBox2.currentText
        # Reset Combo boxes
        self.fillColorsComboBox(self.planeComboBox1)
        self.fillColorsComboBox(self.planeComboBox2)
        self.planeComboBox2.removeItem(self.planeComboBox2.findText(colorPlane1))
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

    def modify(self, obj, event):
        self.defineAngle(self.planeComboBox1.currentText, self.planeComboBox2.currentText)

    def defineAngle(self, colorPlane1, colorPlane2):
        print "DEFINE ANGLE"
        print colorPlane1
        if colorPlane1 in self.logic.ColorNodeCorrespondence:
            slice1 = slicer.util.getNode(self.logic.ColorNodeCorrespondence[colorPlane1])
            self.logic.getMatrix(slice1)
            slice1.SetWidgetVisible(True)
            slice1.SetSliceVisible(True)
            matrix1 = self.logic.getMatrix(slice1)
            normal1 = self.logic.defineNormal(matrix1)
        else:
            normal1 = self.planeControlsDictionary[colorPlane1].logic.N

        print colorPlane2
        if colorPlane2 in self.logic.ColorNodeCorrespondence:
            slice2 = slicer.util.getNode(self.logic.ColorNodeCorrespondence[colorPlane2])
            self.logic.getMatrix(slice2)
            slice2.SetWidgetVisible(True)
            slice2.SetSliceVisible(True)
            matrix2 = self.logic.getMatrix(slice2)
            normal2 = self.logic.defineNormal(matrix2)
        else:
            normal2 = self.planeControlsDictionary[colorPlane2].logic.N

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

            customPlanes = tempDictionary["customPlanes"]

            for key, fidlist in customPlanes.items():
                self.addNewPlane(key)
                tempkey = "Plane " + str(self.planeControlsId)
                currentFidList = self.planeControlsDictionary[tempkey].logic.getFiducialList()
                for i in range(0, len(fidlist)):
                    f = fidlist[i]
                    currentFidList.AddFiducial(f[0], f[1], f[2])

            fileObj.close()


# This widget controls each of the planes that are added to the interface.
# The widget contains its own logic, i.e. an object of AnglePlanesLogic. 
# Each plane contains a separate fiducial list. The planes are named P1, P2, ..., PN. The landmarks are named
# P1-1, P1-2, P1-N. 
class AnglePlanesWidgetPlaneControl(qt.QFrame):
    def __init__(self, anglePlanes, id, pointlocatordictionary):
        qt.QFrame.__init__(self)
        self.id = id

        self.setLayout(qt.QFormLayout())
        self.pointLocatorDictionary = pointlocatordictionary
        self.logic = AnglePlanesLogic(id)

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

        numberOfNodes = len(anglePlanes.getPositionOfModelNodes(True))
        self.surfaceDeplacementCheckBox = qt.QCheckBox("On Surface")
        if numberOfNodes > 0:
            self.surfaceDeplacementCheckBox.setChecked(True)
        else:
            self.surfaceDeplacementCheckBox.setDisabled(True)
        self.surfaceDeplacementCheckBox.connect('stateChanged(int)', self.onSurfaceDeplacementStateChanged)
        planeLabelLayout.addWidget(self.surfaceDeplacementCheckBox)


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

        # fiducial list for the plane

        fidNode = self.logic.getFiducialList()
        for i in range(0, fidNode.GetNumberOfFiducials()):
            label = fidNode.GetNthFiducialLabel(i)
            landmark1ComboBox.addItem(label)
            landmark2ComboBox.addItem(label)
            landmark3ComboBox.addItem(label)

            anglePlanes.landmarkComboBox1MidPoint.addItem(label)
            anglePlanes.landmarkComboBox2MidPoint.addItem(label)
            #anglePlanes.midPointFiducialDictionaryID[label] = fidNode.GetNthMarkupID(i)

        fidNode.onFiducialAddedObserverTag = fidNode.AddObserver(fidNode.MarkupAddedEvent, self.onFiducialAdded)
        fidNode.onFiducialRemovedObserverTag = fidNode.AddObserver(fidNode.MarkupRemovedEvent, self.onFiducialRemoved)

        fidNode.setPointModifiedEventObserverTag = fidNode.AddObserver(fidNode.PointModifiedEvent,
                                                                       self.onPointModifiedEvent)

        # These observers are in AnglePlaneWidgets, they listen to any fiducial being added
        # 
        fidNode.onFiducialAddedMidPointObserverTag = fidNode.AddObserver(fidNode.MarkupAddedEvent,
                                                                         anglePlanes.onFiducialChangedMidPoint)
        fidNode.onFiducialRemovedMidPointObserverTag = fidNode.AddObserver(fidNode.MarkupRemovedEvent,
                                                                           anglePlanes.onFiducialChangedMidPoint)

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

        self.HidePlaneCheckBox = qt.QCheckBox("Hide")
        self.HidePlaneCheckBox.setChecked(False)
        self.HidePlaneCheckBox.connect('stateChanged(int)', self.onHideSurface)
        landmarkSliderLayout.addWidget(self.HidePlaneCheckBox)

        self.layout().addRow(landmarkSliderLayout)

        removeButtonLayout = qt.QHBoxLayout()
        removeButtonLayout.addStretch(1)
        removePlaneButton = qt.QPushButton("Remove")
        removeButtonLayout.addWidget(removePlaneButton)
        self.removeFiducials = qt.QCheckBox("Remove Fiducials")
        self.removeFiducials.setChecked(True)
        removeButtonLayout.addWidget(self.removeFiducials)
        self.layout().addRow(removeButtonLayout)
        removePlaneButton.connect('clicked(bool)', self.onRemove)

        self.anglePlanes = anglePlanes


    def PlaneIsDefined(self):
        if self.landmark1ComboBox.currentIndex > 0 and self.landmark2ComboBox.currentIndex > 0 and self.landmark3ComboBox.currentIndex > 0:
            return True
        else:
            return False

    def onRemove(self):
        self.logic.remove()
        self.anglePlanes.RemoveManualPlane(self.id)

    def onFiducialRemoved(self, obj, event):
        fidlist = obj
        # Update combo boxes
        for i in range(1, self.landmark1ComboBox.count):
            found = self.fiducialInList(self.landmark1ComboBox.itemText(i), fidlist)
            if not found:
                self.landmark1ComboBox.removeItem(i)
                self.landmark2ComboBox.removeItem(i)
                self.landmark3ComboBox.removeItem(i)
                break
        # Update middle point dictionary
        # Check that the fiducial that was remove was not a middle fiducial
        for x in self.anglePlanes.middleFiducialDictionary.keys():
            node = slicer.mrmlScene.GetNodeByID(self.anglePlanes.middleFiducialDictionary[x].nodeID)
            if node == fidlist:
                if node.GetMarkupIndexByID(x) == -1:
                    print "removing fiducial from middlefiducialDictionary"
                    del self.anglePlanes.middleFiducialDictionary[x]
                    # continue
        # If fiducial that is removed is one of the two fiducials defining my middle point,
        # we also remove the middle point
        # If this loop removes a markup, this might start an asynchrone job that might modify
        # the dictionary while we iterate. This would be an issue.
        middleFiducialDictionary = copy.deepcopy(self.anglePlanes.middleFiducialDictionary)
        for x in middleFiducialDictionary.keys():
            node = slicer.mrmlScene.GetNodeByID(middleFiducialDictionary[x].nodeID)
            p1 = middleFiducialDictionary[x].P1
            p2 = middleFiducialDictionary[x].P2
            if node.GetMarkupIndexByID(p1) == -1 or node.GetMarkupIndexByID(p2) == -1:
                position = node.GetMarkupIndexByID(x)
                if position != -1:
                    print "removing middle fiducial because end point has been removed"
                    node.RemoveMarkup(position)
                    # No need to remove it from middleFiducialDictionary here as the previous
                    # call should trigger the call of this function and remove this markup
                    # from middleFiducialDictionary for us



    def getFiducials(self):

        fidNode = self.logic.getFiducialList()

        listCoord = list()

        coord = numpy.zeros(3)
        fidNode.GetNthFiducialPosition(int(self.landmark1ComboBox.currentIndex) - 1, coord)
        listCoord.append(coord)

        fidNode.GetNthFiducialPosition(int(self.landmark2ComboBox.currentIndex) - 1, coord)
        listCoord.append(coord)

        fidNode.GetNthFiducialPosition(int(self.landmark3ComboBox.currentIndex) - 1, coord)
        listCoord.append(coord)

        return listCoord

    def placePlaneClicked(self):
        self.anglePlanes.valueComboBox()
        self.update()

    def fiducialInList(self, name, fidlist):
        for i in range(0, fidlist.GetNumberOfFiducials()):
            if name == fidlist.GetNthFiducialLabel(i):
                return True
        return False

    def projectAllFiducials(self):
        fidlist = self.logic.getFiducialList()
        for i in range(0, fidlist.GetNumberOfFiducials()):
            fidid = fidlist.GetNthMarkupID(i)
            isMiddlePoint = fidid in self.anglePlanes.middleFiducialDictionary.keys()
            if not isMiddlePoint:
                self.projectFiducialOnClosestSurface(fidlist, i, self.pointLocatorDictionary)

    def UpdateMiddlePointsPositions(self):
        current = numpy.zeros(3)
        for x in self.anglePlanes.middleFiducialDictionary.keys():
            middleFiducial = self.anglePlanes.middleFiducialDictionary[x]
            if middleFiducial.nodeID == self.logic.getFiducialList().GetID():
                node = slicer.mrmlScene.GetNodeByID(middleFiducial.nodeID)
                self.anglePlanes.computeMidPointPosition(node, middleFiducial.P1, middleFiducial.P2, current)
                node.RemoveObserver(node.setPointModifiedEventObserverTag)
                index = node.GetMarkupIndexByID(x)
                node.SetNthFiducialPosition(index, current[0], current[1], current[2])
                node.setPointModifiedEventObserverTag = node.AddObserver(node.PointModifiedEvent,
                                                                           self.onPointModifiedEvent)
                if middleFiducial.onSurface:
                    print "middle on surface"
                    self.projectFiducialOnClosestSurface(node, index, self.pointLocatorDictionary)

    def onPointModifiedEvent(self, obj, event):
        if self.surfaceDeplacementCheckBox.isChecked():
            self.projectAllFiducials()
        self.update()

    def onSurfaceDeplacementStateChanged(self):
        if self.surfaceDeplacementCheckBox.isChecked():
            self.projectAllFiducials()
            self.update()

    def onHideSurface(self):
        if self.PlaneIsDefined():
            if self.HidePlaneCheckBox.isChecked():
                self.logic.planeLandmarks(self.landmark1ComboBox.currentIndex, self.landmark2ComboBox.currentIndex,
                                          self.landmark3ComboBox.currentIndex, self.slider.value, 0)
            else:
                self.logic.planeLandmarks(self.landmark1ComboBox.currentIndex, self.landmark2ComboBox.currentIndex,
                                          self.landmark3ComboBox.currentIndex, self.slider.value,
                                          self.slideOpacity.value)

    def update(self):
        self.UpdateMiddlePointsPositions()
        if self.PlaneIsDefined():
            self.logic.planeLandmarks(self.landmark1ComboBox.currentIndex, self.landmark2ComboBox.currentIndex,
                                      self.landmark3ComboBox.currentIndex, self.slider.value, self.slideOpacity.value)

    def projectFiducialOnClosestSurface(self, fidlist, fidid, pointLocatorDictionary):

        landmarkCoord = numpy.zeros(3)

        fidlist.GetNthFiducialPosition(fidid, landmarkCoord)
        minDistance = slicer.sys.float_info.max
        minClosestPoint = numpy.zeros(3)

        # print "landmark: " + str(landmarkCoord) + ", fidid: " + str(fidid)
        keys = pointLocatorDictionary.keys()
        foundCloser = False
        for i in range(0, len(keys)):

            locator = pointLocatorDictionary[keys[i]]

            closestpointid = locator.FindClosestPoint(landmarkCoord)

            mrmlmodelcollection = slicer.mrmlScene.GetNodesByClassByName("vtkMRMLModelNode", keys[i])
            modelnode = mrmlmodelcollection.GetItemAsObject(0)
            if not modelnode:
                continue
            poly = modelnode.GetPolyData()
            if poly is None or not hasattr(poly, 'GetPoints'): #  It will be equal to None if object does not contain a polydata
                continue
            closestpoint = poly.GetPoints().GetPoint(closestpointid)
            #print "closestpointid:" + str(closestpointid) + ", point: " + str(closestpoint)

            distance = numpy.linalg.norm(closestpoint - landmarkCoord)

            #print "distance: " + str(distance)

            if distance < minDistance:
                foundCloser = True
                minDistance = distance
                minClosestPoint = closestpoint
        if foundCloser:
            if minClosestPoint[0] != landmarkCoord[0] or minClosestPoint[1] != landmarkCoord[1] or minClosestPoint[2] != \
                    landmarkCoord[2]:
                fidlist.RemoveObserver(fidlist.setPointModifiedEventObserverTag)
                fidlist.SetNthFiducialPosition(fidid, minClosestPoint[0], minClosestPoint[1], minClosestPoint[2])
                fidlist.setPointModifiedEventObserverTag = fidlist.AddObserver(fidlist.PointModifiedEvent,
                                                                           self.onPointModifiedEvent)

    def addLandMarkClicked(self):
        # print "Add landmarks"
        # # Place landmarks in the 3D scene
        fidlist = self.logic.getFiducialList()
        selectionNode = slicer.mrmlScene.GetNodeByID("vtkMRMLSelectionNodeSingleton")
        selectionNode.SetReferenceActivePlaceNodeClassName("vtkMRMLMarkupsFiducialNode")
        selectionNode.SetActivePlaceNodeID(fidlist.GetID())
        # print selectionNode
        interactionNode = slicer.mrmlScene.GetNodeByID("vtkMRMLInteractionNodeSingleton")
        interactionNode.SetCurrentInteractionMode(1)
        # To select multiple points in the 3D view, we want to have to click
        # on the "place fiducial" button multiple times
        placeModePersistence = 0
        interactionNode.SetPlaceModePersistence(placeModePersistence)

    def onFiducialAdded(self, obj, event):
        fidlist = obj
        label = fidlist.GetNthFiducialLabel(fidlist.GetNumberOfFiducials() - 1)

        self.landmark1ComboBox.addItem(label)
        self.landmark2ComboBox.addItem(label)
        self.landmark3ComboBox.addItem(label)


class AnglePlanesLogic(ScriptedLoadableModuleLogic):
    def __init__(self, id=-1):
        self.ColorNodeCorrespondence = {'Red': 'vtkMRMLSliceNodeRed',
                                        'Yellow': 'vtkMRMLSliceNodeYellow',
                                        'Green': 'vtkMRMLSliceNodeGreen'}
        self.id = id
        self.initialize()

    def initialize(self):
        self.polydata = vtk.vtkPolyData()
        self.points = vtk.vtkPoints()
        self.planeSource = vtk.vtkPlaneSource()
        self.mapper = vtk.vtkPolyDataMapper()
        self.actor = vtk.vtkActor()

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


    def getFiducialList(self):

        P = self.getFiducialListName()
        nodes = slicer.mrmlScene.GetNodesByClassByName('vtkMRMLMarkupsFiducialNode', P)
        if nodes.GetNumberOfItems() == 0:
            # The list does not exist so we create it

            fidNode = slicer.vtkMRMLMarkupsFiducialNode()
            fidNode.SetName(P)
            slicer.mrmlScene.AddNode(fidNode)

        else:
            # The list exists but the observers must be updated
            fidNode = nodes.GetItemAsObject(0)
        return fidNode

    def getFiducialListName(self):
        return "P" + str(self.id)

    def getMatrix(self, slice):
        self.mat = slice.GetSliceToRAS()
        print self.mat
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

        if (norm1_RL == 0 or norm1_RL == 0):
            self.angle_degre_RL = 0
            self.angle_degre_RL_comp = 0
        else:
            scalar_product_RL = (normalVect1[1] * normalVect2[1] + normalVect1[2] * normalVect2[2])
            #print "scalar product : \n", scalar_product_RL

            angleRL = acos(scalar_product_RL / (norm1_RL * norm2_RL))
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

            angleSI = acos(scalar_product_SI / (norm1_SI * norm2_SI))
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

            angleAP = acos(scalar_product_AP / (norm1_AP * norm2_AP))

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

        # print "Vn = ",Vn

        norm_Vn = sqrt(Vn[0] * Vn[0] + Vn[1] * Vn[1] + Vn[2] * Vn[2])

        Normal = Vn / norm_Vn

        #print "N = ",Normal

        return Normal

    def planeLandmarks(self, Landmark1Value, Landmark2Value, Landmark3Value, slider, sliderOpacity):
        # Limit the number of 3 landmarks to define a plane
        # Keep the coordinates of the landmarks
        fidNode = self.getFiducialList()

        r1 = 0
        a1 = 0
        s1 = 0
        coord = numpy.zeros(3)

        if Landmark1Value != 0:
            fidNode.GetNthFiducialPosition(int(Landmark1Value) - 1, coord)
            r1 = coord[0]
            a1 = coord[1]
            s1 = coord[2]


        # Limit the number of 3 landmarks to define a plane
        # Keep the coordinates of the landmarks
        r2 = 0
        a2 = 0
        s2 = 0
        if Landmark2Value != 0:
            fidNode.GetNthFiducialPosition(int(Landmark2Value) - 1, coord)
            r2 = coord[0]
            a2 = coord[1]
            s2 = coord[2]

        # Limit the number of 3 landmarks to define a plane
        # Keep the coordinates of the landmarks
        r3 = 0
        a3 = 0
        s3 = 0
        if Landmark3Value != 0:
            fidNode.GetNthFiducialPosition(int(Landmark3Value) - 1, coord)
            r3 = coord[0]
            a3 = coord[1]
            s3 = coord[2]

        points = self.points
        if points.GetNumberOfPoints() == 0:
            points.InsertNextPoint(r1, a1, s1)
            points.InsertNextPoint(r2, a2, s2)
            points.InsertNextPoint(r3, a3, s3)
        else:
            points.SetPoint(0, r1, a1, s1)
            points.SetPoint(1, r2, a2, s2)
            points.SetPoint(2, r3, a3, s3)

        polydata = self.polydata
        polydata.SetPoints(points)

        centerOfMass = vtk.vtkCenterOfMass()
        centerOfMass.SetInputData(polydata)
        centerOfMass.SetUseScalarsAsWeights(False)
        centerOfMass.Update()

        G = centerOfMass.GetCenter()

        # print "Center of mass = ",G

        A = (r1, a1, s1)
        B = (r2, a2, s2)
        C = (r3, a3, s3)

        # Vector GA
        GA = numpy.matrix([[0], [0], [0]])
        GA[0] = A[0] - G[0]
        GA[1] = A[1] - G[1]
        GA[2] = A[2] - G[2]

        #print "GA = ", GA

        # Vector BG
        GB = numpy.matrix([[0], [0], [0]])
        GB[0] = B[0] - G[0]
        GB[1] = B[1] - G[1]
        GB[2] = B[2] - G[2]

        #print "GB = ", GB

        # Vector CG
        GC = numpy.matrix([[0], [0], [0]])
        GC[0] = C[0] - G[0]
        GC[1] = C[1] - G[1]
        GC[2] = C[2] - G[2]

        #print "GC = ", GC

        self.N = self.normalLandmarks(GA, GB)

        D = numpy.matrix([[0], [0], [0]])
        E = numpy.matrix([[0], [0], [0]])
        F = numpy.matrix([[0], [0], [0]])

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

        planeSource = self.planeSource
        planeSource.SetNormal(self.N[0], self.N[1], self.N[2])

        planeSource.SetOrigin(D[0], D[1], D[2])
        planeSource.SetPoint1(E[0], E[1], E[2])
        planeSource.SetPoint2(F[0], F[1], F[2])

        planeSource.Update()

        plane = planeSource.GetOutput()

        mapper = self.mapper
        mapper.SetInputData(plane)
        mapper.Update()

        self.actor.SetMapper(mapper)
        self.actor.GetProperty().SetColor(0, 0.4, 0.8)
        self.actor.GetProperty().SetOpacity(sliderOpacity)

        renderer = list()
        renderWindow = list()
        layoutManager = slicer.app.layoutManager()
        for i in range(0, layoutManager.threeDViewCount):
            threeDWidget = layoutManager.threeDWidget(i)
            threeDView = threeDWidget.threeDView()
            renderWindow.append(threeDView.renderWindow())
            renderers = renderWindow[i].GetRenderers()
            renderer.append(renderers.GetFirstRenderer())
            renderer[i].AddViewProp(self.actor)
            renderWindow[i].AddRenderer(renderer[i])
            renderer[i].Render()
            renderWindow[i].Render()


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

        fidlist1.AddFiducial(10, 10, 10)
        fidlist1.AddFiducial(20, 20, 20)
        fidlist1.AddFiducial(10, 20, 30)

        fidlist2 = slicer.mrmlScene.GetNodesByClassByName('vtkMRMLMarkupsFiducialNode', "P2").GetItemAsObject(0)

        fidlist2.AddFiducial(50, 50, 50)
        fidlist2.AddFiducial(40, 20, 80)
        fidlist2.AddFiducial(10, 40, 20)

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

