# Flood, Darkcurrent file, flux file
Some cycle-specific configuration files are located at following locations

MP_DIR = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2025B_mp/" #2025B means the cycle. as of 2026-3-3 we are at 2026A cycle. but haven't prepared the 2026A_mp folder yet. if such is the case, use the most recent one.
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


# NATURAL LANGUAGE → COMMAND EXAMPLES
The examples below teach the LLM how to translate natural language into CLI commands.
Use the "Full catalog runs" provided in session context to look up run numbers by title.
When the user refers to a sample by name, find its run number from the catalog context.

CRITICAL — SAMPLE NAME MATCHING RULES:
All --sample matching (/set --sample, /remove --sample, /show table --sample,
/remove all --keep, /stitch removerow --sample) uses this rule:
  - No wildcard: EXACT match (case-insensitive). "empty" matches only "empty", NOT "emptycupbox".
  - With * or ?: glob-style wildcard (case-insensitive). "empty*" matches "empty", "emptycupbox".
    "*3b*" matches "S-3b", "S-3b-2". "Test-SR-?" matches "Test-SR-0", "Test-SR-1".

Examples:
  - "remove empty from table" → /remove --sample empty  (exact, only "empty")
  - "remove all empty* samples" → /remove --sample empty*  (wildcard, "empty" + "emptycupbox" etc.)
  - "set trans for all 3b samples" → /set --sample *3b* trans 172804  (wildcard, matches S-3b etc.)
  - "keep only porsil" → /remove all --keep porsil  (exact, keeps only "porsil")
  - "keep all porsil samples" → /remove all --keep porsil*  (wildcard)
  - "remove SDS samples from stitch" → /stitch removerow --sample SDS*  (if SDS-1, SDS-2 etc.)

ALWAYS check the "Samples:" list in session context to determine whether exact or wildcard is needed.
If the user says a name that exactly matches one sample, use exact. If they use a prefix/partial
name that implies multiple samples, add * wildcard.

## SHOW TABLE (CRITICAL — "show me" means DISPLAY, never delete/remove)
- "show me emptycupbob from the table" → /show table --sample emptycupbob
- "show porsil rows" → /show table --sample porsil
- "show me the 3b samples" → /show table --sample 3b
- "display only banjo runs" → /show table --sample banjo
- "what does the emptycupbob row look like" → /show table --sample emptycupbob
- "show the whole table" → /show table
IMPORTANT: When the user says "show me <sample>" or "display <sample>", ALWAYS use /show table --sample.
NEVER use /remove to "show" something. /remove is ONLY for explicit deletion requests like "delete", "remove", "drop".

## SET — field reference
Each working table row has these independent run association fields:
  trans       → transmission_run     (this sample's own transmission measurement)
  bkg         → background_scatt     (background scattering run, e.g. banjo/empty cell)
  bkgtrans    → background_trans     (the transmission OF the background sample)
  emp         → empty_beam           (empty beam / direct beam run)
  thickness   → thickness            (sample thickness in cm)
Each /set command changes ONLY the specified field. They are independent.
"trans" is the sample's transmission. "bkgtrans" is the background's transmission. These are different runs.

## SET — single row
- "set transmission for run 172815 to 172804" → /set 172815 trans 172804
- "clear background for 172815" → /set 172815 bkg none
- "set thickness to 0.1 for run 172815" → /set 172815 thickness 0.1
- "change row 3's background transmission to 172941" → /set 3 bkgtrans 172941
- "set background scattering for row 5 to 172940" → /set 5 bkg 172940

## SET — bulk by sample name
- "apply transmission 172804 to all 3b runs" → /set --sample 3b trans 172804
- "set background to 172940 for all porsil" → /set --sample porsil bkg 172940
- "set background transmission to 172941 for all porsil" → /set --sample porsil bkgtrans 172941
- "clear transmission for all empty runs" → /set --sample empty trans none
- "set thickness 0.1 for all S-3b" → /set --sample 3b thickness 0.1
- "use 172804 as trans for all samples containing poursil" → /set --sample poursil trans 172804
- "set empty beam 172900 for everything" → requires one /set --sample per distinct sample name
NOTE: /set --sample matches by case-insensitive substring. "3b" matches "S-3b", "S-3b-2", etc.
- "T-b should be transmission for all S-3b* samples" → For all T-b (transmission) run from different configuration, find all scattering sample name with S-3b* then apply T-b of corresponding configuration as transmission.

## ASSIGN BKG — PREFERRED for background reassignment
/assign bkg <sample_name> is the PREFERRED command when the user wants to set a sample
as background for ALL rows. It handles configuration matching automatically in code
(deterministic, no LLM lookup needed) and sets BOTH bkg and bkgtrans in one command.

CRITICAL RULE — ALWAYS prefer /assign bkg over per-row /set for background:
  - "use emptyticell as background for all samples" → /assign bkg emptyticell
  - "set emptyticell as background" → /assign bkg emptyticell
  - "change background to emptycupbob" → /assign bkg emptycupbob
  - "use s0 as background" → /assign bkg s0
  - "reassign background to banjo" → /assign bkg banjo

/assign bkg automatically:
  1. Finds scattering (S-) and transmission (T-) runs for the named sample in the catalog
  2. Matches by configuration — each row gets the bkg run from its OWN config
  3. Sets both bkg (background scattering) and bkgtrans (background transmission)
  4. Gives the background sample itself the empty beam as its background

Use per-row /set commands ONLY when:
  - Setting background for a SPECIFIC SUBSET of rows (not all), e.g. "use X as bkg for only the 3b samples"
  - Setting a single field (only bkg or only bkgtrans, not both)
  - The user gives an explicit run number, not a sample name

## SET — smart lookup from catalog context
When the user refers to runs by title instead of number, look up the run number from the
"Full catalog runs" section in the session context. The catalog lists every run as:
  <run_number> <title> [<config_id>]

CRITICAL RULE — CONFIGURATION MATCHING (for /set with run lookups):
Every run in the catalog belongs to a specific configuration (e.g. 4m10a, 2.5m2.5a, 8m12a).
When assigning transmission or empty beam to a sample row via /set, you MUST use a run
from the SAME configuration as that sample row. NEVER assign a run from a different config.

For background assignment, PREFER /assign bkg (see above). Only use per-row /set for
background when targeting a specific subset of rows.

The configuration matching rule applies to transmission and empty beam assignments:
  "use X as transmission" → find T-X from the same config as each target row
  "use X as empty beam" → find S-X or the empty beam run from the same config

When there is only ONE configuration in the table, /set --sample is fine.
When there are MULTIPLE configurations, you MUST emit per-row /set commands matching by config.

Example flows:
- User: "use emptyticell as background for all samples"
  → /assign bkg emptyticell
  (ONE command — handles config matching, bkg+bkgtrans automatically)

- User: "use emptycupbob as background for all 3b_SR samples"
  This targets a SUBSET, so use per-row /set (not /assign bkg which affects ALL rows):
  For EACH 3b_SR row, find S-emptycupbob and T-emptycupbob from the catalog with MATCHING config.
  Emit per-row commands:
     /set <row1_run> bkg <emptycupbob_scatt_same_config>
     /set <row1_run> bkgtrans <emptycupbob_trans_same_config>
     ... (one pair per matching row)

- User: "remove background from sample 31"
  → means CLEAR the bkg and bkgtrans fields (not delete the row):
  /set --sample 31 bkg none
  /set --sample 31 bkgtrans none

- User: "apply transmission from porsil to all empty beam rows"
  1. For each "empty" row, find T-porsil from the catalog with the SAME config as that row
  2. Emit per-row: /set <row_run> trans <T-porsil_same_config>

- User: "change background transmission for all 3b to 172941"
  → /set --sample *3b* bkgtrans 172941
  (only changes bkgtrans, does NOT touch bkg or trans)
  NOTE: This is OK with --sample because the user gave an explicit run number, no config lookup needed.

# REDUCTION TABLE Manipulation
- "remove Test-series from the table" → /remove --sample Test

## STITCH
- "set all stitch target to 1" → /stitch set all target 1
- "set all stitch target to 4m10a" → /stitch set all target 4m10a
- "set stitch target for all samples to 4m10a" → /stitch set all target 4m10a
- "set target index to 0 for all" → /stitch set all target 0
- "change the reference target to 2.5m2.5a for all samples" → /stitch set all target 2.5m2.5a
- "set overlap for all to 0.01 0.02" → /stitch set all overlap 0.01 0.02
- "auto overlap for all" → /stitch set all overlap auto
- "set mysample target to 4m10a" → /stitch set mysample target 4m10a
- "remove 4m10a from the stitch table" → /stitch removeconfig all 4m10a
- "remove 4m2.5a config from stitch" → /stitch removeconfig all 4m2.5a
- "remove 4m10a from row 2" → /stitch removeconfig 2 4m10a
- "remove row 3 from stitch" → /stitch removerow 3
- "remove SDS samples from stitch table" → /stitch removerow --sample SDS
- "remove all stitch rows with banjo" → /stitch removerow --sample banjo
- "remove row 3 from stitch, then auto overlap, then run" →
  /stitch removerow 3
  /stitch set all overlap auto
  /stitch run
- "reorder configs to conf0,conf1" → /stitch reorder all conf0,conf1
- "swap the config order in row 2 to highq,lowq" → /stitch reorder 2 highq,lowq
- "reorder all stitch groups to 8m12a,4m10a,4m2.5a" → /stitch reorder all 8m12a,4m10a,4m2.5a
- "change config order for row 0" → /stitch reorder 0 <configs in desired order>
NOTE: When user says "all" or "the stitch table" in context of stitch, use literal "all" as the sample/idx parameter.
The target can be either an integer index (0, 1, 2) or a config_id string (4m10a, 2.5m2.5a).
When removing a config by name, ALWAYS use "all" as the index unless the user specifies a row number.

## AUTOPILOT
- "autopilot ipts 34648" → /autopilot 34648
- "run autopilot for ipts 34648 only for Bi1 samples" → /autopilot 34648 --samples Bi1
- "reduce only Bi1 and Bi2 in ipts 34648 using autopilot" → /autopilot 34648 --samples Bi1,Bi2
- "autopilot 35884 just sample S1" → /autopilot 35884 --samples S1
- "reduce all data except Y5 from ipts 36548" → /autopilot 36548 --exclude Y5
- "autopilot 36548 except Y5 and Y6" → /autopilot 36548 --exclude Y5,Y6
- "reduce everything in 35884 but skip banjo" → /autopilot 35884 --exclude banjo
- "reduce all except Y5 from 36548, all thickness 0.1 cm" → /autopilot 36548 --exclude Y5  (0.1 is the default, no --thickness needed)
- "reduce all from 36548, all samples thickness 0.15 cm" → /autopilot 36548 --thickness 0.15
- "autopilot 35884, thickness 0.2 for all" → /autopilot 35884 --thickness 0.2
- "autopilot 35884, use banjo as background" → /autopilot 35884 --bkg banjo
- "autopilot 35884, use emptyticell as bkg, skip Y5" → /autopilot 35884 --bkg emptyticell --exclude Y5
- "reduce only 8m configuration from 35884" → /autopilot 35884 --config 8m12a
- "autopilot 36548, only the 4m10a config, thickness 0.2" → /autopilot 36548 --config 4m10a --thickness 0.2
- "reduce 35884 with s0 as background for 8m only" → /autopilot 35884 --bkg s0 --config 8m12a
CRITICAL: Default thickness is 0.1 cm. If user says 0.1 cm, do NOT generate a separate /set thickness command.
  When user says thickness X where X != 0.1, use --thickness X in the autopilot command itself.
  This keeps everything atomic — one command, no timing issues.
NOTE: All flags are applied AFTER matchruns, BEFORE reduction.
  Execution order: --thickness → --bkg → --samples → --exclude → --config
  Setup (thickness, bkg) runs first on the full table so all rows get correct values.
  Filters (samples, exclude, config) run after to trim down what gets reduced.
  When user says "except" or "all except" or "but skip", use --exclude, NOT --samples *.
NEVER use --samples * — it does not work. Use --exclude to remove specific samples.
When user mentions a background sample, use --bkg (not a separate /assign bkg command).
When user mentions a specific config to reduce, use --config (not a separate /remove command).

## SETTINGS
- "set parallel jobs to 2" → /settings multiprocessing 2
- "use 3 parallel reductions" → /settings multiprocessing 3
- "enable multiprocessing" → /settings multiprocessing 4
- "disable parallel reduction" → /settings multiprocessing 1
- "run reductions in parallel" → /settings multiprocessing 4
- "set multiprocessing to 2" → /settings multiprocessing 2
- "turn off multiprocessing" → /settings multiprocessing 1
- "how many parallel jobs?" → CHAT MODE: check session state for max_workers value
NOTE: Default is 1 (sequential). Maximum is 4. When user says "enable" without a number, use 4.
