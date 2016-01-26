import os
from __main__ import vtk, qt, ctk, slicer
import numpy
from slicer.ScriptedLoadableModule import *


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
        self.normal = None
        # -------------- interface -------------------
        qt.QFrame.__init__(self)
        # UI setup
        loader = qt.QUiLoader()
        moduleName = 'AnglePlanes'
        scriptedModulesPath = eval('slicer.modules.%s.path' % moduleName.lower())
        scriptedModulesPath = os.path.dirname(scriptedModulesPath)
        path = os.path.join(scriptedModulesPath, 'Resources', 'UI', 'PlaneControl.ui')
        qfile = qt.QFile(path)
        widget = loader.load(qfile)
        self.widget = widget
        # self.anglePlanes.layout.addWidget(widget)

        self.planeLabel = self.logic.findWidget(self.widget, "planeLabel")
        self.planeLabel = qt.QLabel('Plane ' + str(id) + ":")
        self.addFiducialButton = self.logic.findWidget(self.widget, "addFiducialButton")
        self.landmark1ComboBox = self.logic.findWidget(self.widget, "landmark1ComboBox")
        self.landmark2ComboBox = self.logic.findWidget(self.widget, "landmark2ComboBox")
        self.landmark3ComboBox = self.logic.findWidget(self.widget, "landmark3ComboBox")
        self.slideOpacity = self.logic.findWidget(self.widget, "slideOpacity")
        self.AdaptToBoundingBoxCheckBox = self.logic.findWidget(self.widget, "AdaptToBoundingBoxCheckBox")
        self.HidePlaneCheckBox = self.logic.findWidget(self.widget, "HidePlaneCheckBox")
        self.removePlaneButton = self.logic.findWidget(self.widget, "removePlaneButton")
        # connections
        self.addFiducialButton.connect('clicked()', self.addLandMarkClicked)
        self.landmark1ComboBox.connect('currentIndexChanged(QString)', self.placePlaneClicked)
        self.landmark2ComboBox.connect('currentIndexChanged(QString)', self.placePlaneClicked)
        self.landmark3ComboBox.connect('currentIndexChanged(QString)', self.placePlaneClicked)
        self.slideOpacity.connect('valueChanged(double)', self.placePlaneClicked)
        self.AdaptToBoundingBoxCheckBox.connect('stateChanged(int)', self.onBBox)
        self.AdaptToBoundingBoxCheckBox.connect('stateChanged(int)',self.placePlaneClicked)
        self.HidePlaneCheckBox.connect('stateChanged(int)', self.update)
        self.removePlaneButton.connect('clicked(bool)', self.onRemove)
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
                self.normal = self.logic.planeLandmarks(self.fidlist,
                                          self.landmark1ComboBox.currentText, self.landmark2ComboBox.currentText,
                                          self.landmark3ComboBox.currentText, self.normal,
                                          self.AdaptToBoundingBoxCheckBox,
                                          0, self.planeCollection, self.actor)
            else:
                self.normal = self.logic.planeLandmarks(self.fidlist,
                                          self.landmark1ComboBox.currentText, self.landmark2ComboBox.currentText,
                                          self.landmark3ComboBox.currentText, self.normal,
                                          self.AdaptToBoundingBoxCheckBox,
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