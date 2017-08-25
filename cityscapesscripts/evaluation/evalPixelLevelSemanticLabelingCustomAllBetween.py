#!/usr/bin/python
#
# The evaluation script for pixel-level semantic labeling.
# We use this script to evaluate your approach on the test set.
# You can use the script to evaluate on the validation set.
#
# Please check the description of the "getPrediction" method below 
# and set the required environment variables as needed, such that 
# this script can locate your results.
# If the default implementation of the method works, then it's most likely
# that our evaluation server will be able to process your results as well.
#
# Note that the script is a lot faster, if you enable cython support.
# WARNING: Cython only tested for Ubuntu 64bit OS.
# To enable cython, run
# setup.py build_ext --inplace
#
# To run this script, make sure that your results are images,
# where pixels encode the class IDs as defined in labels.py.
# Note that the regular ID is used, not the train ID.
# Further note that many classes are ignored from evaluation.
# Thus, authors are not expected to predict these classes and all
# pixels with a ground truth label that is ignored are ignored in
# evaluation.

# python imports
from __future__ import print_function
import os, sys
import platform
import fnmatch

try:
    from itertools import izip
except ImportError:
    izip = zip

try:
    from PIL import PILLOW_VERSION
except:
    print("Please install the module 'Pillow' for image processing, e.g.")
    print("pip install pillow")
    sys.exit(-1)

try:
    import PIL.Image     as Image
    import PIL.ImageDraw as ImageDraw
except:
    print("Failed to import the image processing packages.")
    sys.exit(-1)

# Cityscapes imports
sys.path.append( os.path.normpath( os.path.join( os.path.dirname( __file__ ) , '..' , 'helpers' ) ) )
from csHelpers import *

# C Support
# Enable the cython support for faster evaluation
# Only tested for Ubuntu 64bit OS
CSUPPORT = True
# Check if C-Support is available for better performance
if CSUPPORT:
    try:
        import addToConfusionMatrix
    except:
        CSUPPORT = False


###################################
# PLEASE READ THESE INSTRUCTIONS!!!
###################################
# Provide the prediction file for the given ground truth file.
#
# The current implementation expects the results to be in a certain root folder.
# This folder is one of the following with decreasing priority:
#   - environment variable CITYSCAPES_RESULTS
#   - environment variable CITYSCAPES_DATASET/results
#   - ../../results/"
#
# Within the root folder, a matching prediction file is recursively searched.
# A file matches, if the filename follows the pattern
# <city>_123456_123456*.png
# for a ground truth filename
# <city>_123456_123456_gtFine_labelIds.png
def getPrediction( args, groundTruthFile ):
    # determine the prediction path, if the method is first called
    if not args.predictionPath:
        rootPath = None
        if 'CITYSCAPES_RESULTS' in os.environ:
            rootPath = os.environ['CITYSCAPES_RESULTS']
        elif 'CITYSCAPES_DATASET' in os.environ:
            rootPath = os.path.join( os.environ['CITYSCAPES_DATASET'] , "results" )
        else:
            rootPath = os.path.join(os.path.dirname(os.path.realpath(__file__)),'..','..','results')

        if not os.path.isdir(rootPath):
            printError("Could not find a result root folder. Please read the instructions of this method.")

        args.predictionPath = rootPath

    # walk the prediction path, if not happened yet
    if not args.predictionWalk:
        walk = []
        for root, dirnames, filenames in os.walk(args.predictionPath):
            walk.append( (root,filenames) )
        args.predictionWalk = walk

    csFile = getCsFileInfo(groundTruthFile)
    filePattern = "{}_{}_gtFine_labelIds*.png".format( csFile.city , csFile.sequenceNb , csFile.frameNb )

    #print("pred",args.predictionWalk,"","\n")
    predictionFiles = []
    for root, filenames in args.predictionWalk:
        for filename in fnmatch.filter(filenames, filePattern):
            predictionFiles.append(os.path.join(root, filename))
                #printError("Found multiple predictions for ground truth {}".format(groundTruthFile))

    if not predictionFiles:
        return [];
        #printError("Found no prediction for ground truth {}".format(groundTruthFile))

    return predictionFiles


######################
# Parameters
######################


# A dummy class to collect all bunch of data
class CArgs(object):
    pass
# And a global object of that class
args = CArgs()

# Where to look for Cityscapes
if 'CITYSCAPES_DATASET' in os.environ:
    args.cityscapesPath = os.environ['CITYSCAPES_DATASET']
else:
    args.cityscapesPath = os.path.join(os.path.dirname(os.path.realpath(__file__)),'..','..')

# Parameters that should be modified by user
args.exportFile         = os.path.join( args.cityscapesPath , "evaluationResults" , "resultPixelLevelSemanticLabeling.json" )
args.groundTruthSearch  = os.path.join( args.cityscapesPath , "gtFine" , "train" , "*", "*_gtFine_labelIds.png" )

# Remaining params
args.evalInstLevelScore = True
args.evalPixelAccuracy  = False
args.evalLabels         = []
args.printRow           = 5
args.normalized         = True
args.colorized          = hasattr(sys.stderr, "isatty") and sys.stderr.isatty() and platform.system()=='Linux'
args.bold               = colors.BOLD if args.colorized else ""
args.nocol              = colors.ENDC if args.colorized else ""
args.JSONOutput         = True
args.quiet              = False

args.avgClassSize       = {
    "bicycle"    :  4672.3249222261 ,
    "caravan"    : 36771.8241758242 ,
    "motorcycle" :  6298.7200839748 ,
    "rider"      :  3930.4788056518 ,
    "bus"        : 35732.1511111111 ,
    "train"      : 67583.7075812274 ,
    "car"        : 12794.0202738185 ,
    "person"     :  3462.4756337644 ,
    "truck"      : 27855.1264367816 ,
    "trailer"    : 16926.9763313609 ,
}

# store some parameters for finding predictions in the args variable
# the values are filled when the method getPrediction is first called
args.predictionPath = None
args.predictionWalk = None


#########################
# Methods
#########################


# Generate empty confusion matrix and create list of relevant labels
def generateMatrix(args):
    args.evalLabels = []
    for label in labels:
        if (label.id < 0):
            continue
        # we append all found labels, regardless of being ignored
        args.evalLabels.append(label.id)
    maxId = max(args.evalLabels)
    # We use longlong type to be sure that there are no overflows
    return np.zeros(shape=(maxId+1, maxId+1),dtype=np.ulonglong)

def generateInstanceStats(args):
    instanceStats = {}
    instanceStats["classes"   ] = {}
    instanceStats["categories"] = {}
    for label in labels:
        if label.hasInstances and not label.ignoreInEval:
            instanceStats["classes"][label.name] = {}
            instanceStats["classes"][label.name]["tp"] = 0.0
            instanceStats["classes"][label.name]["tpWeighted"] = 0.0
            instanceStats["classes"][label.name]["fn"] = 0.0
            instanceStats["classes"][label.name]["fnWeighted"] = 0.0
    for category in category2labels:
        labelIds = []
        allInstances = True
        for label in category2labels[category]:
            if label.id < 0:
                continue
            if not label.hasInstances:
                allInstances = False
                break
            labelIds.append(label.id)
        if not allInstances:
            continue

        instanceStats["categories"][category] = {}
        instanceStats["categories"][category]["tp"] = 0.0
        instanceStats["categories"][category]["tpWeighted"] = 0.0
        instanceStats["categories"][category]["fn"] = 0.0
        instanceStats["categories"][category]["fnWeighted"] = 0.0
        instanceStats["categories"][category]["labelIds"] = labelIds

    return instanceStats


# Get absolute or normalized value from field in confusion matrix.
def getMatrixFieldValue(confMatrix, i, j, args):
    if args.normalized:
        rowSum = confMatrix[i].sum()
        if (rowSum == 0):
            return float('nan')
        return float(confMatrix[i][j]) / rowSum
    else:
        return confMatrix[i][j]

# Calculate and return IOU score for a particular label
def getIouScoreForLabel(label, confMatrix, args):
    if id2label[label].ignoreInEval:
        return float('nan'),float('nan')

    # the number of true positive pixels for this label
    # the entry on the diagonal of the confusion matrix
    tp = np.longlong(confMatrix[label,label])

    # the number of false negative pixels for this label
    # the row sum of the matching row in the confusion matrix
    # minus the diagonal entry
    gt = np.longlong(confMatrix[label,:].sum());
    fn = gt - tp

    # the number of false positive pixels for this labels
    # Only pixels that are not on a pixel with ground truth label that is ignored
    # The column sum of the corresponding column in the confusion matrix
    # without the ignored rows and without the actual label of interest
    notIgnored = [l for l in args.evalLabels if not id2label[l].ignoreInEval and not l==label]
    fp = np.longlong(confMatrix[notIgnored,label].sum())

    # the denominator of the IOU score
    denom = (tp + fp + fn)
    if denom == 0:
        return float('nan'),float('nan')

    # return IOU
    return float(tp) / denom , gt

# Calculate and return IOU score for a particular label
def getInstanceIouScoreForLabel(label, confMatrix, instStats, args):
    if id2label[label].ignoreInEval:
        return float('nan'),float('nan')

    labelName = id2label[label].name
    if not labelName in instStats["classes"]:
        return float('nan'),float('nan')

    tp = instStats["classes"][labelName]["tpWeighted"]
    fn = instStats["classes"][labelName]["fnWeighted"]
    gt = tp+fn
    # false postives computed as above
    notIgnored = [l for l in args.evalLabels if not id2label[l].ignoreInEval and not l==label]
    fp = np.longlong(confMatrix[notIgnored,label].sum())

    # the denominator of the IOU score
    denom = (tp + fp + fn)
    if denom == 0:
        return float('nan'),float('nan')

    # return IOU
    return float(tp) / denom , gt

# Calculate prior for a particular class id.
def getPrior(label, confMatrix):
    return float(confMatrix[label,:].sum()) / confMatrix.sum()

# Get average of scores.
# Only computes the average over valid entries.
def getScoreAverage(scoreList, args):
    validScores = 0
    scoreSum    = 0.0
    for score in scoreList:
        if not math.isnan(scoreList[score][0]):
            validScores += 1
            scoreSum += scoreList[score][0]
    if validScores == 0:
        return float('nan')
    return scoreSum / validScores

# Get weighted average of scores.
# Only computes the average over valid entries.
def getFreqScoreAverage(scoreList, args):
    validScores = 0
    scoreSum    = 0.0
    for score in scoreList:
        if not math.isnan(scoreList[score][0]):
            validScores += scoreList[score][1]
            scoreSum += scoreList[score][0]*scoreList[score][1]
    if validScores == 0:
        return float('nan')
    return scoreSum / validScores

# Calculate and return IOU score for a particular category
def getIouScoreForCategory(category, confMatrix, args):
    # All labels in this category
    labels = category2labels[category]
    # The IDs of all valid labels in this category
    labelIds = [label.id for label in labels if not label.ignoreInEval and label.id in args.evalLabels]
    # If there are no valid labels, then return NaN
    if not labelIds:
        return float('nan'),float('nan')

    # the number of true positive pixels for this category
    # this is the sum of all entries in the confusion matrix
    # where row and column belong to a label ID of this category
    tp = np.longlong(confMatrix[labelIds,:][:,labelIds].sum())

    # the number of false negative pixels for this category
    # that is the sum of all rows of labels within this category
    # minus the number of true positive pixels
    fn = np.longlong(confMatrix[labelIds,:].sum()) - tp

    # the number of false positive pixels for this category
    # we count the column sum of all labels within this category
    # while skipping the rows of ignored labels and of labels within this category
    notIgnoredAndNotInCategory = [l for l in args.evalLabels if not id2label[l].ignoreInEval and id2label[l].category != category]
    fp = np.longlong(confMatrix[notIgnoredAndNotInCategory,:][:,labelIds].sum())

    # the denominator of the IOU score
    denom = (tp + fp + fn)
    if denom == 0:
        return float('nan'),float('nan')

    # return IOU
    return float(tp) / denom, tp+fn

# Calculate and return IOU score for a particular category
def getInstanceIouScoreForCategory(category, confMatrix, instStats, args):
    if not category in instStats["categories"]:
        return float('nan'),float('nan')
    labelIds = instStats["categories"][category]["labelIds"]

    tp = instStats["categories"][category]["tpWeighted"]
    fn = instStats["categories"][category]["fnWeighted"]

    # the number of false positive pixels for this category
    # same as above
    notIgnoredAndNotInCategory = [l for l in args.evalLabels if not id2label[l].ignoreInEval and id2label[l].category != category]
    fp = np.longlong(confMatrix[notIgnoredAndNotInCategory,:][:,labelIds].sum())

    # the denominator of the IOU score
    denom = (tp + fp + fn)
    if denom == 0:
        return float('nan'),float('nan')

    # return IOU
    return float(tp) / denom,tp+fn


# create a dictionary containing all relevant results
def createResultDict( confMatrix, classScores, classInstScores, categoryScores, categoryInstScores, perImageStats, args ):
    # write JSON result file
    wholeData = {}
    wholeData["confMatrix"] = confMatrix.tolist()
    wholeData["priors"] = {}
    wholeData["labels"] = {}
    for label in args.evalLabels:
        wholeData["priors"][id2label[label].name] = getPrior(label, confMatrix)
        wholeData["labels"][id2label[label].name] = label
    wholeData["classScores"] = classScores
    wholeData["classInstScores"] = classInstScores
    wholeData["categoryScores"] = categoryScores
    wholeData["categoryInstScores"] = categoryInstScores
    wholeData["averageScoreClasses"] = getScoreAverage(classScores, args)
    wholeData["averageScoreInstClasses"] = getScoreAverage(classInstScores, args)
    wholeData["averageScoreCategories"] = getScoreAverage(categoryScores, args)
    wholeData["averageScoreInstCategories"] = getScoreAverage(categoryInstScores, args)

    if perImageStats:
        wholeData["perImageScores"] = perImageStats

    return wholeData

def writeJSONFile(wholeData, args):
    path = os.path.dirname(args.exportFile)
    ensurePath(path)
    writeDict2JSON(wholeData, args.exportFile)

# Print confusion matrix
def printConfMatrix(confMatrix, args):
    # print line
    print("\b{text:{fill}>{width}}".format(width=15, fill='-', text=" "), end=' ')
    for label in args.evalLabels:
        print("\b{text:{fill}>{width}}".format(width=args.printRow + 2, fill='-', text=" "), end=' ')
    print("\b{text:{fill}>{width}}".format(width=args.printRow + 3, fill='-', text=" "))

    # print label names
    print("\b{text:>{width}} |".format(width=13, text=""), end=' ')
    for label in args.evalLabels:
        print("\b{text:^{width}} |".format(width=args.printRow, text=id2label[label].name[0]), end=' ')
    print("\b{text:>{width}} |".format(width=6, text="Prior"))

    # print line
    print("\b{text:{fill}>{width}}".format(width=15, fill='-', text=" "), end=' ')
    for label in args.evalLabels:
        print("\b{text:{fill}>{width}}".format(width=args.printRow + 2, fill='-', text=" "), end=' ')
    print("\b{text:{fill}>{width}}".format(width=args.printRow + 3, fill='-', text=" "))

    # print matrix
    for x in range(0, confMatrix.shape[0]):
        if (not x in args.evalLabels):
            continue
        # get prior of this label
        prior = getPrior(x, confMatrix)
        # skip if label does not exist in ground truth
        if prior < 1e-9:
            continue

        # print name
        name = id2label[x].name
        if len(name) > 13:
            name = name[:13]
        print("\b{text:>{width}} |".format(width=13,text=name), end=' ')
        # print matrix content
        for y in range(0, len(confMatrix[x])):
            if (not y in args.evalLabels):
                continue
            matrixFieldValue = getMatrixFieldValue(confMatrix, x, y, args)
            print(getColorEntry(matrixFieldValue, args) + "\b{text:>{width}.2f}  ".format(width=args.printRow, text=matrixFieldValue) + args.nocol, end=' ')
        # print prior
        print(getColorEntry(prior, args) + "\b{text:>{width}.4f} ".format(width=6, text=prior) + args.nocol)
    # print line
    print("\b{text:{fill}>{width}}".format(width=15, fill='-', text=" "), end=' ')
    for label in args.evalLabels:
        print("\b{text:{fill}>{width}}".format(width=args.printRow + 2, fill='-', text=" "), end=' ')
    print("\b{text:{fill}>{width}}".format(width=args.printRow + 3, fill='-', text=" "), end=' ')

# Print intersection-over-union scores for all classes.
def printClassScores(scoreList, instScoreList, args):
    if (args.quiet):
        return
    print(args.bold + "classes          IoU      nIoU" + args.nocol)
    print("--------------------------------")
    for label in args.evalLabels:
        if (id2label[label].ignoreInEval):
            continue
        labelName = str(id2label[label].name)
        iouStr = getColorEntry(scoreList[labelName][0], args) + "{val:>5.3f}".format(val=scoreList[labelName][0]) + args.nocol
        niouStr = getColorEntry(instScoreList[labelName][0], args) + "{val:>5.3f}".format(val=instScoreList[labelName][0]) + args.nocol
        print("{:<14}: ".format(labelName) + iouStr + "    " + niouStr)

# Print intersection-over-union scores for all categorys.
def printCategoryScores(scoreDict, instScoreDict, args):
    if (args.quiet):
        return
    print(args.bold + "categories       IoU      nIoU" + args.nocol)
    print("--------------------------------")
    for categoryName in scoreDict:
        if all( label.ignoreInEval for label in category2labels[categoryName] ):
            continue
        iouStr  = getColorEntry(scoreDict[categoryName][0], args) + "{val:>5.3f}".format(val=scoreDict[categoryName][0]) + args.nocol
        niouStr = getColorEntry(instScoreDict[categoryName][0], args) + "{val:>5.3f}".format(val=instScoreDict[categoryName][0]) + args.nocol
        print("{:<14}: ".format(categoryName) + iouStr + "    " + niouStr)

# Gives percent of correctly annotated pixels out of all
def evaluatePixelAccuracy(confMatrix):
    allTruePositives = 0;
    nonVoidPixels = 0
    for label in args.evalLabels :
        if label < 7  :
            continue
        nonVoidPixels += np.longlong(confMatrix[label , : ].sum())
        allTruePositives += np.longlong(confMatrix[label,label])

    print("")
    allNonEdgeTruePositives = 0;
    nonEdgePixels = 0
    for label in args.evalLabels:
        if label < 4 : # Havenot included license plate also.
            continue
        labelPixelSum = np.longlong(confMatrix[label, :].sum())
        nonEdgePixels += np.longlong(confMatrix[label, :].sum())
        allNonEdgeTruePositives += np.longlong(confMatrix[label, label])
    evaluatePixelError(confMatrix,allNonEdgeTruePositives)
    evaluateTrueVsOtherPixError(confMatrix,allNonEdgeTruePositives)
    print("~~~~~");
    print("Percent of (Truely labeled pixels/ All nonVoid pixels) : ",(allTruePositives*100.0)/nonVoidPixels)
    print("Percent of (Truely labeled pixels/ All nonEdge pixels) : ",(allNonEdgeTruePositives * 100.0) /nonEdgePixels )
    print("~~~~~~~")     

#Evaluating Pixel Error Relation Metric
def evaluatePixelError(confMatrix, totalPixelCt):
    print("")
    print("Description : For each label gives top 5 mis matched labels.")
    print("For each label : we give (percent of mismatch w.r.t GT label) (percentage pixel mismatch w.r.t the image)\n")
    for label in args.evalLabels:
        if label < 4 : # Have not included licence plate alos.
            continue
        labelPixelSum = np.longlong(confMatrix[label, :].sum())
        name = id2label[label].name
        print("{name:>{width}} --> ".format(width=13,name=name),end=' ')
        if labelPixelSum <= 0.000 :
            print("{text:>13}".format(text="----"))
        else :
            sortedArrayIndices = np.argsort(np.array(confMatrix[label, :]))[::-1]
            ct = 0;
            for index in range(sortedArrayIndices.size) :
                eleIdx = sortedArrayIndices[index]
                if eleIdx == label :
                     continue;
                ct = ct+1
                if(ct == 5) :
                    break     
                eleName = id2label[eleIdx].name
                if len(eleName) > 13 :
                     eleName = eleName[:13]
                overallPixelError = (float(confMatrix[label, eleIdx])*100)/totalPixelCt
                print("{text:>13} ({val:4.3f}) ({pixError:0.4f})".format(val=((float(confMatrix[label, eleIdx])*100)/labelPixelSum),pixError=overallPixelError, text=eleName), end=' ')
            print("")

#Evaluate top true vs other pixel error
def evaluateTrueVsOtherPixError(confMatrix, totalPixelCt) :
    print("\n Desc: Gives top 20 maximum pixel error w.r.t given image of true label marked as some other label ")
    print("Format :  True Label  Other Label  (Percentage pixel error wrt Image)  (No of error Pixels)\n")
    arr = np.array(confMatrix)
    #print(arr.shape)
    sorted2dArray = np.dstack(np.unravel_index(np.argsort(arr.ravel()), confMatrix.shape)).squeeze(0)[::-1]
    #print(sorted2dArray.size)
    #print(sorted2dArray)
    ct = 0;
    for idx in range(sorted2dArray.shape[0]) :
        pair = sorted2dArray[idx]
        #print(pair)

        if (pair[0] == pair[1]) or pair[0] < 4 or pair[1] < 4:
            continue
        ct = ct+1;
        if(ct == 90) :
            break;   
        trueLable = id2label[pair[0]].name
        wrongLable = id2label[pair[1]].name
        pixError = float(confMatrix[pair[0]][pair[1]]) 
        print("{gtLabel:>13}(gtLabel) ------ {wrongLabel:13} ({pixErrorPercentage:0.4f}) ({pixError:0.4f})".format(gtLabel=trueLable,wrongLabel=wrongLable,pixErrorPercentage=(pixError*100)/totalPixelCt,pixError=pixError), end="\n")

# Evaluate image lists pairwise.
def evaluateImgLists(predictionImgList, groundTruthImgList, args):
    if len(predictionImgList) != len(groundTruthImgList):
        printError("List of images for prediction and groundtruth are not of equal size.")
    confMatrix    = generateMatrix(args)
    instStats     = generateInstanceStats(args)
    perImageStats = {}
    nbPixels      = 0

    if not args.quiet:
        print("Evaluating {} pairs of images...".format(len(predictionImgList)))

    # Evaluate all pairs of images and save them into a matrix
    for i in range(len(predictionImgList)):
        predictionImgFileName = predictionImgList[i]
        groundTruthImgFileName = groundTruthImgList[i]
        print("Evaluate ", predictionImgFileName, "<>", groundTruthImgFileName)
        nbPixels += evaluatePair(predictionImgFileName, groundTruthImgFileName, confMatrix, instStats, perImageStats, args)

        # sanity check
        if confMatrix.sum() != nbPixels:
            printError('Number of analyzed pixels and entries in confusion matrix disagree: contMatrix {}, pixels {}'.format(confMatrix.sum(),nbPixels))

        if not args.quiet:
            print("\rImages Processed: {}".format(i+1), end=' ')
            sys.stdout.flush()
    if not args.quiet:
        print("\n")

    #create new image


    # sanity check
    if confMatrix.sum() != nbPixels:
        printError('Number of analyzed pixels and entries in confusion matrix disagree: contMatrix {}, pixels {}'.format(confMatrix.sum(),nbPixels))

    # print confusion matrix
    if (not args.quiet):
        printConfMatrix(confMatrix, args)
    evaluatePixelAccuracy(confMatrix)


    # Calculate IOU scores on class level from matrix
    classScoreList = {}
    for label in args.evalLabels:
        labelName = id2label[label].name
        classScoreList[labelName] = getIouScoreForLabel(label, confMatrix, args)

    # Calculate instance IOU scores on class level from matrix
    classInstScoreList = {}
    for label in args.evalLabels:
        labelName = id2label[label].name
        classInstScoreList[labelName] = getInstanceIouScoreForLabel(label, confMatrix, instStats, args)

    # Print IOU scores
    if (not args.quiet):
        print("")
        print("")
        printClassScores(classScoreList, classInstScoreList, args)
        iouAvgStr  = getColorEntry(getScoreAverage(classScoreList, args), args) + "{avg:5.3f}".format(avg=getScoreAverage(classScoreList, args)) + args.nocol
        niouAvgStr = getColorEntry(getScoreAverage(classInstScoreList , args), args) + "{avg:5.3f}".format(avg=getScoreAverage(classInstScoreList , args)) + args.nocol
	wiouAvgStr = getColorEntry(getFreqScoreAverage(classScoreList , args), args) + "{avg:5.3f}".format(avg=getFreqScoreAverage(classScoreList , args)) + args.nocol
	wniouAvgStr = getColorEntry(getFreqScoreAverage(classInstScoreList , args), args) + "{avg:5.3f}".format(avg=getFreqScoreAverage(classInstScoreList , args)) + args.nocol
        print("--------------------------------")
        print("Score Average : " + iouAvgStr + "    " + niouAvgStr)
        print("--------------------------------")
	print("W-Score Avg   : " + wiouAvgStr + "    " + wniouAvgStr)
        print("--------------------------------")
        print("")

    # Calculate IOU scores on category level from matrix
    categoryScoreList = {}
    for category in category2labels.keys():
        categoryScoreList[category] = getIouScoreForCategory(category,confMatrix,args)

    # Calculate instance IOU scores on category level from matrix
    categoryInstScoreList = {}
    for category in category2labels.keys():
        categoryInstScoreList[category] = getInstanceIouScoreForCategory(category,confMatrix,instStats,args)

    # Print IOU scores
    if (not args.quiet):
        print("")
        printCategoryScores(categoryScoreList, categoryInstScoreList, args)
        iouAvgStr = getColorEntry(getScoreAverage(categoryScoreList, args), args) + "{avg:5.3f}".format(avg=getScoreAverage(categoryScoreList, args)) + args.nocol
        niouAvgStr = getColorEntry(getScoreAverage(categoryInstScoreList, args), args) + "{avg:5.3f}".format(avg=getScoreAverage(categoryInstScoreList, args)) + args.nocol
	wiouAvgStr = getColorEntry(getFreqScoreAverage(categoryScoreList, args), args) + "{avg:5.3f}".format(avg=getFreqScoreAverage(categoryScoreList, args)) + args.nocol
	wniouAvgStr = getColorEntry(getFreqScoreAverage(categoryInstScoreList, args), args) + "{avg:5.3f}".format(avg=getFreqScoreAverage(categoryInstScoreList, args)) + args.nocol
        print("--------------------------------")
        print("Score Average : " + iouAvgStr + "    " + niouAvgStr)
        print("--------------------------------")
	print("W-Score Avg   : " + wiouAvgStr  + "    " + wniouAvgStr)
        print("--------------------------------")
        print("")

    # write result file
    allResultsDict = createResultDict( confMatrix, classScoreList, classInstScoreList, categoryScoreList, categoryInstScoreList, perImageStats, args )
    writeJSONFile( allResultsDict, args)

    # return confusion matrix
    return allResultsDict

# Main evaluation method. Evaluates pairs of prediction and ground truth
# images which are passed as arguments.
def evaluatePair(predictionImgFileName, groundTruthImgFileName, confMatrix, instanceStats, perImageStats, args):
    # Loading all resources for evaluation.
    try:
        predictionImg = Image.open(open(predictionImgFileName,'rb'))
        predictionNp  = np.array(predictionImg)
    except:
        printError("Unable to load " + predictionImgFileName)
    try:
        groundTruthImg = Image.open(groundTruthImgFileName)
        groundTruthNp = np.array(groundTruthImg)
    except:
        printError("Unable to load " + groundTruthImgFileName)
    # load ground truth instances, if needed
    if args.evalInstLevelScore:
        groundTruthInstanceImgFileName = groundTruthImgFileName.replace("labelIds","instanceIds")
        try:
            instanceImg = Image.open(groundTruthInstanceImgFileName)
            instanceNp  = np.array(instanceImg)
        except:
            printError("Unable to load " + groundTruthInstanceImgFileName)

    #print("width",predictionImgFileName,predictionImg.size[0],groundTruthImg.size[0])
    # Check for equal image sizes
    if (predictionImg.size[0] != groundTruthImg.size[0]):
        printError("Image widths of " + predictionImgFileName + " and " + groundTruthImgFileName + " are not equal.")
    if (predictionImg.size[1] != groundTruthImg.size[1]):
        printError("Image heights of " + predictionImgFileName + " and " + groundTruthImgFileName + " are not equal.")
    if ( len(predictionNp.shape) != 2 ):
        printError("Predicted image has multiple channels.")

    imgWidth  = predictionImg.size[0]
    imgHeight = predictionImg.size[1]
    nbPixels  = imgWidth*imgHeight

    # Evaluate images
    if (CSUPPORT):
        # using cython
        confMatrix = addToConfusionMatrix.cEvaluatePair(predictionNp, groundTruthNp, confMatrix, args.evalLabels)
    else:
        # the slower python way
        for (groundTruthImgPixel,predictionImgPixel) in izip(groundTruthImg.getdata(),predictionImg.getdata()):
            if (not groundTruthImgPixel in args.evalLabels):
                printError("Unknown label with id {:}".format(groundTruthImgPixel))

            confMatrix[groundTruthImgPixel][predictionImgPixel] += 1

    if args.evalInstLevelScore:
        # Generate category masks
        categoryMasks = {}
        for category in instanceStats["categories"]:
            categoryMasks[category] = np.in1d( predictionNp , instanceStats["categories"][category]["labelIds"] ).reshape(predictionNp.shape)

        instList = np.unique(instanceNp[instanceNp > 1000])
        for instId in instList:
            labelId = int(instId/1000)
            label = id2label[ labelId ]
            if label.ignoreInEval:
                continue

            mask = instanceNp==instId
            instSize = np.count_nonzero( mask )

            tp = np.count_nonzero( predictionNp[mask] == labelId )
            fn = instSize - tp

            weight = args.avgClassSize[label.name] / float(instSize)
            tpWeighted = float(tp) * weight
            fnWeighted = float(fn) * weight

            instanceStats["classes"][label.name]["tp"]         += tp
            instanceStats["classes"][label.name]["fn"]         += fn
            instanceStats["classes"][label.name]["tpWeighted"] += tpWeighted
            instanceStats["classes"][label.name]["fnWeighted"] += fnWeighted

            category = label.category
            if category in instanceStats["categories"]:
                catTp = 0
                catTp = np.count_nonzero( np.logical_and( mask , categoryMasks[category] ) )
                catFn = instSize - catTp

                catTpWeighted = float(catTp) * weight
                catFnWeighted = float(catFn) * weight

                instanceStats["categories"][category]["tp"]         += catTp
                instanceStats["categories"][category]["fn"]         += catFn
                instanceStats["categories"][category]["tpWeighted"] += catTpWeighted
                instanceStats["categories"][category]["fnWeighted"] += catFnWeighted

    if args.evalPixelAccuracy:
        notIgnoredLabels = [l for l in args.evalLabels if not id2label[l].ignoreInEval]
        notIgnoredPixels = np.in1d( groundTruthNp , notIgnoredLabels , invert=True ).reshape(groundTruthNp.shape)
        erroneousPixels = np.logical_and( notIgnoredPixels , ( predictionNp != groundTruthNp ) )
        perImageStats[predictionImgFileName] = {}
        perImageStats[predictionImgFileName]["nbNotIgnoredPixels"] = np.count_nonzero(notIgnoredPixels)
        perImageStats[predictionImgFileName]["nbCorrectPixels"]    = np.count_nonzero(erroneousPixels)

    return nbPixels

# The main method
def main(argv):
    global args

    predictionImgList = []
    groundTruthImgList = []

    # the image lists can either be provided as arguments
    if (len(argv) > 3):
        for arg in argv:
            if ("gt" in arg or "groundtruth" in arg):
                groundTruthImgList.append(arg)
            elif ("pred" in arg):
                predictionImgList.append(arg)
    # however the no-argument way is prefered
    elif len(argv) == 0:
        # use the ground truth search string specified above
        groundTruthImgList = []  # = glob.glob(args.groundTruthSearch)
        groundTruthImgListCopy = glob.glob(args.groundTruthSearch)
        if not groundTruthImgListCopy:
            printError("Cannot find any ground truth images to use for evaluation. Searched for: {}".format(args.groundTruthSearch))
        # get the corresponding prediction for each ground truth imag
        for gt in groundTruthImgListCopy:
            # print("gt0",gt,"","\n");
            elements = getPrediction(args, gt)
            if len(elements) > 0:
                for ele in elements:
                    if gt != ele and ele not in groundTruthImgList:
                        predictionImgList.append(ele)
                        groundTruthImgList.append(gt)
                    # else :
                    # groundTruthImgList.remove(gt)
        print("", len(predictionImgList), "", "\n")

    # evaluate
    evaluateImgLists(predictionImgList, groundTruthImgList, args)

    return

# call the main method
if __name__ == "__main__":
    main(sys.argv[1:])
