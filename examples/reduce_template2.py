#!/usr/bin/env python3
from drtsans.stitch import stitch_profiles
import sys
sys.path.append('/SNS/EQSANS/shared/script/eqsanstools/')
sys.path.append('/SNS/EQSANS/shared/sanstools/sanstools/')
from eqsans_drtsans_script import *
from eqsansplot1d import *
import debye_bueche
import multiplot


from drtsans.dataobjects import load_iqmod, save_iqmod
from drtsans.stitch import stitch_profiles

# Note: This script wrapper is not officially supported by SNS software group
# Instruction:
# To run the script
#source /SNS/software/miniconda2/bin/activate sans 
#   [prompt]$ drtsans yourscriptname.py

# Configuration Files
# /SNS/EQSANS/shared/NeXusFiles/EQSANS/2025A_mp/Sensitivity_patched_thinPMMA_1o3m_158600.nxs
# /SNS/EQSANS/shared/NeXusFiles/EQSANS/2025A_mp/Sensitivity_patched_thinPMMA_2o5m_158599.nxs
# /SNS/EQSANS/shared/NeXusFiles/EQSANS/2025A_mp/Sensitivity_patched_thinPMMA_4m_158598.nxs
# eq._darkfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2025A_mp/EQSANS_158584.nxs.h5"
# eq._beamfluxfilename = "/SNS/EQSANS/shared/mp_tools/2025A_flux/bl6_flux_2025A_Jan_rebinned.txt"
# eq._sampleoffset = 314.5 #default
# eq. _detectoroffset = 80 #default


output_path = "/SNS/EQSANS/IPTS-28870/shared/"

############################
# Reduction of data from IPTS-28870
# 4m 12a config
############################
eq12 = EQVar('2022A/Default.json')  
eq12._defaultjsonfile = '/SNS/EQSANS/shared/script/eqsanstools/eqsans_reduction_qa.json'
eq12._ipts = "28870"
eq12._outputdir = output_path 
eq12._darkfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2022A_mp/EQSANS_129142.nxs.h5"
eq12._maskfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2022A_mp/beamstop_mask_4m_ext.nxs"
eq12._sensitivityfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2022A_mp/Sensitivity_patched_thinPMMA_4m_129588.nxs"
eq12._standardabsolutescale = "7.439464580742"
eq12._thickness = 1.0
eq12._sampleaperturesize = "10"
eq12._detectoroffset = 80.0
eq12._empty = "129560"
eq12._bkgscatt = "129564"
eq12._bkgtrans = "129561"

eq12._qbintype = "log"
eq12._numqbins = 75

############################
# Reduction of data from IPTS-28870
# 4m 2.5a config
############################
eq4 = EQVar('2022A/Default.json')  
eq4._defaultjsonfile = '/SNS/EQSANS/shared/script/eqsanstools/eqsans_reduction_qa.json'
eq4._ipts = "28870"
eq4._outputdir = output_path 
eq4._darkfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2022A_mp/EQSANS_129142.nxs.h5"
eq4._maskfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2022A_mp/beamstop_mask_4m.nxs"
eq4._sensitivityfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2022A_mp/Sensitivity_patched_thinPMMA_4m_129588.nxs"
eq4._standardabsolutescale = "7.439464580742"
eq4._thickness = 1.0
eq4._sampleaperturesize = "10"
eq4._detectoroffset = 80.0
eq4._empty = "129567"
eq4._bkgscatt = "129571"
eq4._bkgtrans = "129568"

eq4._qbintype = "log"
eq4._numqbins = 100


############################
# Reduction of data from IPTS-28870
# 2.5m 2.5A config
############################
eq2 = EQVar('2022A/Default.json')  
eq2._defaultjsonfile = '/SNS/EQSANS/shared/script/eqsanstools/eqsans_reduction_qa.json'
eq2._ipts = "28870"
eq2._outputdir = output_path 
eq2._darkfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2022A_mp/EQSANS_129142.nxs.h5"
eq2._maskfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2022A_mp/beamstop_mask_2o5m.nxs"
eq2._sensitivityfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2022A_mp/Sensitivity_patched_thinPMMA_2o5m_129589.nxs"
eq2._standardabsolutescale = "7.439464580742"
eq2._thickness = 1.0
eq2._sampleaperturesize = "10"
eq2._detectoroffset = 80.0
eq2._empty = "129574"
eq2._bkgscatt = "129578"
eq2._bkgtrans = "129575"

eq2._qbintype = "log"
eq2._numqbins = 200

############################
# Reduction of data from IPTS-28870
# 1.3m 1A config
############################
eq1 = EQVar('2022A/Default.json')  
eq1._defaultjsonfile = '/SNS/EQSANS/shared/script/eqsanstools/eqsans_reduction_qa.json' 
eq1._ipts = "28870"
eq1._outputdir = output_path 
eq1._darkfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2022A_mp/EQSANS_129142.nxs.h5"
eq1._maskfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2022A_mp/beamstop_mask_1o3m.nxs"
eq1._sensitivityfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2022A_mp/Sensitivity_patched_thinPMMA_1o3m_129590.nxs"
eq1._standardabsolutescale = "7.439464580742"
eq1._thickness = 1.0
eq1._sampleaperturesize = "10"
eq1._detectoroffset = 80.0
eq1._empty = "129581"
eq1._bkgscatt = "129585"
eq1._bkgtrans = "129582"

eq1._wavelengthStep = 0.025
eq1._qbintype = "linear"
eq1._numqbins = 100

# the data
scatt4m12 = [129565]
trans4m12 = [129562]

scatt4m = [129572]
trans4m = [129569]

scatt2m = [129579]
trans2m = [129576]

scatt1m = [129586]
trans1m = [129583]

for i in range(0,len(scatt4m)):
    print("...reducing data set #" + str(i+1)  + " at 4m, 12A")
    eq12._samscatt = str(scatt4m12[i])
    eq12._samtrans = str(trans4m12[i])
    eq12._filename = "EQSANS_" + str(scatt4m12[i])
    print(".....reducing " + eq12._samscatt + " for " + eq12._filename)
    reduceNow(eq12) #comment this line in order to skip
    print(".....process complete.")
    
    print("...reducing data set #" + str(i+1)  + " at 4m, 2.5A")
    eq4._samscatt = str(scatt4m[i])
    eq4._samtrans = str(trans4m[i])
    eq4._filename = "EQSANS_" + str(scatt4m[i])
    print(".....reducing " + eq4._samscatt + " for " + eq4._filename)
    reduceNow(eq4) #comment this line in order to skip
    print(".....process complete.")

    print("...reducing data set #" + str(i+1)  + " at 2.5m, 2.5A")
    eq2._samscatt = str(scatt2m[i])
    eq2._samtrans = str(trans2m[i])    
    eq2._filename = "EQSANS_" + str(scatt2m[i])
    print(".....reducing " + eq2._samscatt + " for " + eq2._filename)
    reduceNow(eq2) #comment this line in order to skip
    print(".....process complete.")
    
    print("...reducing data set #" + str(i+1)  + " at 1.3m, 1.0A")
    eq1._samscatt = str(scatt1m[i])

    eq1._samtrans = str(trans1m[i])    
    eq1._filename = "EQSANS_" + str(scatt1m[i])
    print(".....reducing " + eq1._samscatt + " for " + eq1._filename)
    reduceNow(eq1) #comment this line in order to skip
    print(".....process complete.")

    # Stich these two results together
    print(".....finally, data stitching...")
    rlow_q_file = output_path + eq12._filename + "_Iq.dat"
    low_q_file = output_path + eq4._filename + "_Iq.dat"
    mid_q_file = output_path + eq2._filename + "_Iq.dat"
    high_q_file = output_path + eq1._filename + "_Iq.dat"
    rlow_q =load_iqmod(rlow_q_file, sep='\t',header_type='MantidAscii') 
    low_q = load_iqmod(low_q_file, sep='\t',header_type='MantidAscii')
    mid_q = load_iqmod(mid_q_file, sep='\t',header_type='MantidAscii')
    high_q = load_iqmod(high_q_file, sep='\t',header_type='MantidAscii')
    overlap = [0.03,0.05, 0.07,0.15, 0.30,0.45]
    to_stitch = [rlow_q, low_q, mid_q, high_q]
    stitched = stitch_profiles(to_stitch, overlap, target_profile_index=0)
    merged_file = output_path + eq12._filename + "_merged.txt"
    save_iqmod(stitched, merged_file, sep=' ', float_format='%.6E')
    print(".....merged file saved : ", merged_file)
    
    dfile = output_path + eq12._filename+"_merged.txt"
    outfile = output_path + eq12._filename+"_merged"
    multiplot.multiplot(name=[dfile], ofile=outfile, path=output_path)
    dfile = eq12._filename+"_merged.txt"
    debye_bueche.debye_bueche(filename=dfile, path=output_path, qmin=0.01, qmax=0.03)
    
    




