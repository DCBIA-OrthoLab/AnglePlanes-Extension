cmake_minimum_required(VERSION 2.8.9)

project(AnglePlanesExtension)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "https://www.slicer.org/slicerWiki/index.php/Documentation/Nightly/Extensions/AnglePlanes")
set(EXTENSION_CATEGORY "Shape Analysis")
set(EXTENSION_CONTRIBUTORS "Julia Lopinto (University of Michigan), Jean-Baptiste Vimort (University of Michigan)")
set(EXTENSION_DESCRIPTION "This Module is used to calculate the angle between two planes by using the normals. The user gets the choice to use two planes which are already implemented on Slicer or they can define a plane by using landmarks (at least 3 landmarks). Plane can also be saved to be reused for other models.")
set(EXTENSION_ICONURL "https://raw.githubusercontent.com/DCBIA-OrthoLab/AnglePlanes-Extension/master/AnglePlanes.png")
set(EXTENSION_SCREENSHOTURLS "https://www.slicer.org/slicerWiki/images/b/ba/Interface_AnglePlanes.png")

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
# Extension modules
add_subdirectory(AnglePlanes)
## NEXT_MODULE

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})
