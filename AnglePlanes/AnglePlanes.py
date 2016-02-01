import os
from __main__ import vtk, qt, ctk, slicer
import logging
import numpy
import pickle
import AnglePlanesLogic
import PlaneControl
from slicer.ScriptedLoadableModule import *

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
        reload(AnglePlanesLogic)
        reload(PlaneControl)

        self.moduleName = "AnglePlanes"
        self.i = 0
        self.logic = AnglePlanesLogic.AnglePlanesLogic(interface=self)
        self.planeControlsId = 0
        self.planeControlsDictionary = {}
        self.planeCollection = vtk.vtkPlaneCollection()
        self.ignoredNodeNames = ('Red Volume Slice', 'Yellow Volume Slice', 'Green Volume Slice')
        self.colorSliceVolumes = dict()
        self.interactionNode = slicer.mrmlScene.GetNodeByID("vtkMRMLInteractionNodeSingleton")

        # UI setup
        loader = qt.QUiLoader()
        moduleName = 'AnglePlanes'
        scriptedModulesPath = eval('slicer.modules.%s.path' % moduleName.lower())
        scriptedModulesPath = os.path.dirname(scriptedModulesPath)
        path = os.path.join(scriptedModulesPath, 'Resources', 'UI', '%s.ui' %moduleName)

        qfile = qt.QFile(path)
        qfile.open(qt.QFile.ReadOnly)
        widget = loader.load(qfile, self.parent)
        self.layout = self.parent.layout()
        self.widget = widget
        self.layout.addWidget(widget)

        #--------------------------- Scene --------------------------#
        treeView = self.logic.get("treeView")
        treeView.setMRMLScene(slicer.app.mrmlScene())
        treeView.sceneModel().setHorizontalHeaderLabels(["Models"])
        treeView.sortFilterProxyModel().nodeTypes = ['vtkMRMLModelNode']
        treeView.header().setVisible(False)
        self.autoChangeLayout = self.logic.get("autoChangeLayout")
        self.computeBox = self.logic.get("computeBox")
        # -------------------------------Manage planes---------------------------------
        self.CollapsibleButton = self.logic.get("CollapsibleButton")
        self.managePlanesFormLayout = self.logic.get("managePlanesFormLayout")
        self.inputModelSelector = self.logic.get("inputModelSelector")
        self.inputModelSelector.setMRMLScene(slicer.mrmlScene)
        self.inputLandmarksSelector = self.logic.get("inputLandmarksSelector")
        self.inputLandmarksSelector.setMRMLScene(slicer.mrmlScene)
        self.loadLandmarksOnSurfacCheckBox = self.logic.get("loadLandmarksOnSurfacCheckBox")
        self.addPlaneButton = self.logic.get("addPlaneButton")
        self.landmarkComboBox = self.logic.get("landmarkComboBox")
        self.surfaceDeplacementCheckBox = self.logic.get("surfaceDeplacementCheckBox")
        # ----------------- Compute Mid Point -------------
        self.midPointGroupBox = self.logic.get("midPointGroupBox")
        self.selectPlaneForMidPoint = self.logic.get("selectPlaneForMidPoint")
        self.landmarkComboBox1MidPoint = self.logic.get("landmarkComboBox1MidPoint")
        self.landmarkComboBox2MidPoint = self.logic.get("landmarkComboBox2MidPoint")
        self.midPointOnSurfaceCheckBox = self.logic.get("midPointOnSurfaceCheckBox")
        self.defineMiddlePointButton = self.logic.get("defineMiddlePointButton")
        # -------- Choose planes ------------
        self.CollapsibleButtonPlane = self.logic.get("CollapsibleButtonPlane")
        self.planeComboBox1 = self.logic.get("planeComboBox1")
        self.planeComboBox2 = self.logic.get("planeComboBox2")
        # -------- Calculate angles between planes ------------
        self.CollapsibleButton2 = self.logic.get("CollapsibleButton2")
        self.results = self.logic.get("results")
        self.tableResult = self.logic.get("tableResult")
        self.getAngle_RL = qt.QLabel("0")
        self.getAngle_RL.setStyleSheet('QLabel{qproperty-alignment:AlignCenter;}')
        self.getAngle_SI = qt.QLabel("0")
        self.getAngle_SI.setStyleSheet('QLabel{qproperty-alignment:AlignCenter;}')
        self.getAngle_AP = qt.QLabel("0")
        self.getAngle_AP.setStyleSheet('QLabel{qproperty-alignment:AlignCenter;}')
        self.getAngle_RL_comp = qt.QLabel("0")
        self.getAngle_RL_comp.setStyleSheet('QLabel{qproperty-alignment:AlignCenter;}')
        self.getAngle_SI_comp = qt.QLabel("0")
        self.getAngle_SI_comp.setStyleSheet('QLabel{qproperty-alignment:AlignCenter;}')
        self.getAngle_AP_comp = qt.QLabel("0")
        self.getAngle_AP_comp.setStyleSheet('QLabel{qproperty-alignment:AlignCenter;}')
        self.tableResult.setColumnWidth(1, 180)
        self.tableResult.setCellWidget(0, 0, self.getAngle_RL)
        self.tableResult.setCellWidget(0, 1, self.getAngle_RL_comp)
        self.tableResult.setCellWidget(1, 0, self.getAngle_SI)
        self.tableResult.setCellWidget(1, 1, self.getAngle_SI_comp)
        self.tableResult.setCellWidget(2, 0, self.getAngle_AP)
        self.tableResult.setCellWidget(2, 1, self.getAngle_AP_comp)
        # -------------------------------- PLANES --------------------------------#
        self.CollapsibleButton3 = self.logic.get("CollapsibleButton3")
        self.save = self.logic.get("save")
        self.read = self.logic.get("read")
        #-------------------------------- CONNECTIONS --------------------------------#
        self.computeBox.connect('clicked()', self.onComputeBox)
        self.inputModelSelector.connect('currentNodeChanged(vtkMRMLNode*)', self.onModelChanged)
        self.inputLandmarksSelector.connect('currentNodeChanged(vtkMRMLNode*)', self.onLandmarksChanged)
        self.planeComboBox1.connect('currentIndexChanged(QString)', self.valueComboBox)
        self.planeComboBox2.connect('currentIndexChanged(QString)', self.valueComboBox)
        self.addPlaneButton.connect('clicked()', self.addNewPlane)
        self.landmarkComboBox.connect('currentIndexChanged(QString)', self.UpdateInterface)
        self.surfaceDeplacementCheckBox.connect('stateChanged(int)', self.onSurfaceDeplacementStateChanged)
        self.selectPlaneForMidPoint.connect('currentIndexChanged(int)', self.onChangeMiddlePointFiducialNode)
        self.defineMiddlePointButton.connect('clicked()', self.onAddMidPoint)
        self.results.connect('clicked()', self.angleValue)
        self.save.connect('clicked(bool)', self.onSavePlanes)
        self.read.connect('clicked(bool)', self.onReadPlanes)

        slicer.mrmlScene.AddObserver(slicer.mrmlScene.EndCloseEvent, self.onCloseScene)

        for i in self.getPositionOfModelNodes(False):
            modelnode = slicer.mrmlScene.GetNthNodeByClass(i, "vtkMRMLModelNode")
            modelnode.AddObserver(modelnode.DisplayModifiedEvent, self.onChangeModelDisplay)
        ModelAddedClass(self)

        # ------------------------------ INITIALISATION ---------------------------------
        self.fillColorsComboBox(self.planeComboBox1)
        self.fillColorsComboBox(self.planeComboBox2)
        self.planeComboBox1.setCurrentIndex(0)
        self.planeComboBox2.setCurrentIndex(0)
        self.valueComboBox()

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
        planeControls = PlaneControl.AnglePlanesWidgetPlaneControl(self,
                                                      self.planeControlsId,
                                                      self.planeCollection,
                                                      self.inputLandmarksSelector.currentNode())
        self.managePlanesFormLayout.addWidget(planeControls.widget)
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
        self.managePlanesFormLayout.removeWidget(planeControls.widget)
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
        print "--- defineAngle ---"
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
                normal1 = self.planeControlsDictionary[colorPlane1].normal
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
                normal2 = self.planeControlsDictionary[colorPlane2].normal
        else:
            return
        print "normal 1"
        print normal1
        print "normal 2"
        print normal2
        self.logic.getAngle(normal1, normal2)

    def onSavePlanes(self):
        self.logic.savePlanes()

    def onReadPlanes(self):
        self.logic.readPlanes()
        self.onComputeBox()

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

        test = widget.logic.angle_degre_RL != 03.55 or widget.logic.angle_degre_RL_comp != 176.45 or\
               widget.logic.angle_degre_SI != 17.91 or widget.logic.angle_degre_SI_comp != 162.09 or\
               widget.logic.angle_degre_AP != 16.34 or widget.logic.angle_degre_AP_comp != 163.66

        self.delayDisplay('Testing angles')
        if test:

            print "", "Angle", "Complementary"
            print "R-L-View", widget.logic.angle_degre_RL, widget.logic.angle_degre_RL_comp
            print "S-I-View", widget.logic.angle_degre_SI, widget.logic.angle_degre_SI_comp
            print "A-P-View", widget.logic.angle_degre_AP, widget.logic.angle_degre_AP_comp
            self.delayDisplay('Test Failure!')
            return False

        else:
            self.delayDisplay('Test passed!')
            return True
