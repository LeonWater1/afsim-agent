**CUI**

# ballistic demo

This demo illustrates how to create a script to launch various weapons.
Since the processor is a SCRIPT_PROCESSOR, the TRACK variable is not
available as it would be if a TASK_PROCESSOR would have been used.

Variables can be changed in the scenario file to launch at a specific
time (TIME_TO_LAUNCH = XX where XX is sim time in seconds), or make any
launcher fire at a random time (LAUNCH_RANDOM = 1). If launching at a random
time, the MIN_TIME and MAX_TIME variables can be adjusted for each launcher
and the TIME_TO_LAUNCH variable is set to a random time within the min and
max time constraints.
The default times reside in the processors/launch_weapon_processor.txt file.

The weapons fired are ballistic missiles located in ../base_types/weapons/ssm
directory (ie red_srbm_1, red_srbm_2, red_mrbm_2, red_srbm_3, red_srbm_4).

Top-level file is "launch_all.txt".
After running, the replay file to view is "output/launch_all.aer".

## CUI Designation Indicator
* Controlled by: Air Force Research Laboratory
* Controlled by: Aerospace Systems Directorate
* CUI Categories: CTI, EXPT
* LDC/Distribution Statement: DIST-C
* POC: afrl.rq.afsim@us.af.mil

## Notices and Warnings

### DISTRIBUTION STATEMENT C
Distribution authorized to US Government agencies and their contractors;
Critical Technology, Export Controlled; (2021 Mar 10). Other requests for this
information shall be referred to AFRL Aerospace Systems Directorate.

### NOTICE TO ACCOMPANY FOREIGN DISCLOSURE
This content is furnished on the condition that it will not be released to
another nation without specific authority of the Department of the Air Force of
the United States, that it will be used for military purposes only, that
individual or corporate rights originating in the information, whether patented
or not, will be respected, that the recipient will report promptly to the
United States any known or suspected compromise, and that the information will
be provided substantially the same degree of security afforded it by the
Department of Defense of the United States. Also, regardless of any other
markings on the document, it will not be downgraded or declassified without
written approval from the originating U.S. agency.

### WARNING - EXPORT CONTROLLED
This content contains technical data whose export is restricted by the Arms
Export Control Act (Title 22, U.S.C. Sec 2751 et seq.) or the Export
Administration Act of 1979, as amended, Title 50 U.S.C., App. 2401 et seq.
Violations of these export laws are subject to severe criminal penalties.
Disseminate in accordance with provisions of DoD Directive 5230.25.

### HANDLING AND DESTRUCTION NOTICE
Handle this information in accordance with DoDI 5200.48. Destroy by any
approved method that will prevent unauthorized disclosure or reconstruction of
this information in accordance with NIST SP 800-88 and 32 C.F.R 2002.14
(Safeguarding Controlled Unclassified Information).

**CUI**
