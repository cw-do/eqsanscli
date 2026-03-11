# Flood, Darkcurrent file, flux file
Some cycle-specific configuration files are located at following locations

MP_DIR = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2025B_mp/" #2025B means the cycle. as of 2026-3-3 we are at 2026A cycle. but haven't prepared the 2026A_mp folder yet. if such is the case, use the most recent one. 
/show
FLOOD_4m = MP_DIR + "Sensitivity_patched_thinPMMA_4m_167517.nxs" #usually have thinPMMA and detector distance 4m
FLOOD_2o5m = MP_DIR + "Sensitivity_patched_thinPMMA_2o5m_167519.nxs" # for detector distance 2.5m
FLOOD_1o3m = MP_DIR + "Sensitivity_patched_thinPMMA_1o3m_167521.nxs" # for detector distance 1.3m
DARK_FILE = MP_DIR + "EQSANS_167516.nxs.h5"
FLUX_FILE = MP_DIR + "bl6_flux_2025B_Aug_rebinned_4m.txt"

For detector distances longer than 4m, just use FLOOD_4m 


# Other configuration parameters and their rational.
Following parameters are eventually translated into the json parameter. This is just to explain why certain parameter values are used for some of those configuration json parameters (here, the parameter name is not exactly same as json parameter, but there is always a matching parameters (ignore case))
    eq._sampleaperturesize = 10 # aperturesize 10 is usually default unless it's specified.
    eq._maskfilename = ipts_directory + "mask_4m.nxs" # mask files are usually found in the IPTS-{ipts number}/shared/ folder. or current folder. If not found, look for the /SNS/EQSANS/shared/script/eqsanstools/mask_4m.nxs and use it temporarily and let user know. 
    eq._sensitivityfilename = FLOOD_4m # this configuration was 4m or longer detector distance.
    eq._darkfilename = DARK_FILE
    eq._beamfluxfilename = FLUX_FILE 
    eq._numqbins = 40  # for low-q data, usually low numbers are used 40-60 depending on statistics
    eq._qmin = 0.006 # typical q min for 4m 10a 
    eq._qmax = 0.1 # typical qmax cutoff for 4m 10a
    eq._cuttofmin = 1000 # mostly used default value for 4m10a
    eq._cuttofmax = 3000 # mostly used default value for 4m 10a
    eq._wavelengthstep = 0.1 # mostly used default value for all configuration
    eq._fitinelasticincoh = False #usually this  incoherent inelastic correction is not used in low-q configuration. This become important high-q or configurations where there is significant contribution from incoherent background.
    eq._selectminincoh = True #this value is used for the fitinelasticincoh
    eq._incohfit_qmin = 0.025 #this value is used for the fitinelasticincoh this value should be within the q-range of given configuration but not too outside edges. all wavelenth bins should produce q values used in the range of incohfit_qmin and incohfit_qmax
    eq._incohfit_qmax = 0.05
    #eq._incohfit_factor = 4
    #eq._incohfit_intensityweighted = True
    eq._useerrorweighting = True  # usually yes
    eq._qbintype = "log"
    eq._showjson = False
    eq._scalecomponents = scalecomp # this is detector1 scalecomponents array. 
    eq._sampleoffset = samoffset # sample offset
    eq._detectoroffset = detoffset # detector offset: along with scalecomponents, sampleoffset, these values should be avaialble by instrument scientist. usually determined at the beginning of cycle. 




# 4m 10a and 2.5m 2.5a combination experiment
    # 4m 10a configuration
    eq._outputdir = output_directory
    eq._ipts = ipts_number
    eq._standardabsolutescale = 0.227588 #updated 2025-5-5
    eq._sampleaperturesize = 10
    eq._maskfilename = ipts_directory + "mask_4m.nxs"
    eq._sensitivityfilename = flood_4m
    eq._darkfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2025A_mp/EQSANS_158584.nxs.h5"
    eq._beamfluxfilename = "/SNS/EQSANS/shared/mp_tools/2025A_flux/bl6_flux_2025A_Jan_rebinned.txt"
    eq._numqbins = 40
    eq._qmin = 0.006
    eq._qmax = 0.1
    eq._cuttofmin = 1000 # custom tof
    eq._cuttofmax = 3000 # custom tof
    eq._wavelengthstep = 0.1
    eq._fitinelasticincoh = False
    eq._selectminincoh = True
    eq._incohfit_qmin = 0.025
    eq._incohfit_qmax = 0.05
    #eq._incohfit_factor = 4
    #eq._incohfit_intensityweighted = True
    eq._useerrorweighting = True
    eq._qbintype = "log"
    eq._showjson = False
    eq._scalecomponents = scalecomp
    eq._sampleoffset = samoffset
    eq._detectoroffset = detoffset
    if conf ==1 or conf<1:
        eq._empty = emptybeam_1
        eq._thickness = sample_thick[i]
        eq._bkgscatt = str(bkgscatt_1[i])
        eq._bkgtrans = str(bkgtrans_1[i])
        eq._samscatt = str(samscatt_1[i])
        eq._samtrans = str(samtrans_1[i])
        eq._filename = str(sample_names[i])+'_conf1'
        #eq._elasticref = eq._samscatt #elastic reference or elastic corrections are not used often.
        #eq._elasticreftrans = eq._samtrans
        #eq._elasticbkg = eq._bkgtrans 
        #eq._elasticbkgtrans = eq._bkgtrans 
        iqname1 = eq._filename
        reduceNow(eq)


    # 2.5m 2.5a configuration
    eq._outputdir = output_directory
    eq._ipts = ipts_number
    eq._standardabsolutescale = 0.24733770351586978 *1.078*0.7183
    eq._sampleaperturesize = 10
    eq._maskfilename =  ipts_directory + "mask_4m.nxs" # often same mask can be used for different detector distance. 
    eq._sensitivityfilename = flood_2o5m
    eq._darkfilename = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2025A_mp/EQSANS_158584.nxs.h5"
    eq._beamfluxfilename = "/SNS/EQSANS/shared/mp_tools/2025A_flux/bl6_flux_2025A_Jan_rebinned.txt"
    eq._numqbins = 60  #usually at short distance, statistics is better and numbqbins can be higher than low-q data
    eq._qmin = 0.03  # 2.5m 2.5a can provide 0.03 < q < 0.5 
    eq._qmax = 0.4   # here we cut qmax at0.4, more conservatively.
    eq._qbintype = "log"
    eq._showjson = False
    eq._cuttofmin = 2000 # custom tof
    eq._cuttofmax = 11000 # custom tof  these two choices of cuttofmin max values are made to provide monochromatic beam effect. by only looking at narrow wavelength bin, we minimize the inelastic incoherent effect and the high-q curve may look cleaner. This can be used to provide cleaner high-q profile but sacrifice neutron counts. 
    eq._wavelengthstep = 0.1
    eq._fitinelasticincoh = False # since tof cut was used to make monochromatic, fitinelasticincoh doesn't need to be set. if we choose to correct incoherent inelastic effect, then above, we can use cuttofmin=1000, cuttofmax 2000 as default values and use all the wavelength band possible.
    eq._selectminincoh = True
    eq._incohfit_qmin = 0.1
    eq._incohfit_qmax = 0.30
    #eq._incohfit_factor = 4
    #eq._incohfit_intensityweighted = True
    eq._outputwavelengthdependentprofile = True
    eq._useerrorweighting = False
    eq._scalecomponents = scalecomp
    eq._sampleoffset = samoffset
    eq._detectoroffset = detoffset
    if conf==2 or conf<1:
        eq._empty = emptybeam_2
        eq._thickness = sample_thick[i]
        eq._bkgscatt = str(bkgscatt_2[i])
        eq._bkgtrans = str(bkgtrans_2[i])
        eq._samscatt = str(samscatt_2[i])
        eq._samtrans = str(samtrans_2[i])
        eq._filename = str(sample_names[i])+'_conf2_tofcut' # when used custom tofcut, we used to add this post-fix
        iqname2 = eq._filename
        reduceNow(eq)



# following the instrument specific parameter from 202502_agbe/34965/banjo
scalecomp = [1.002, 1.0728155533894388, 1]
detoffset = 84.38081
samoffset = 300 #(banjo rack, ti-rack)
