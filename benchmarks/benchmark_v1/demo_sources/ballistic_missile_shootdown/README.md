**CUI**

# ballistic_missile_shootdown demo

Any resemblance or approximations to actual weapon system capabilities
in this demo are purely coincidental.  The intent of this demo is
to illustrate how to setup a processor to launch an anti-ballistic missile
at sometime in the future to intercept a ballistic missile.
(processors/anti_ballistic_missile_processor.txt)
For the demo, a red_mrbm_1 is launched from Ontario Canada at Washington DC. An anti
ballistic missile (in this case a blue_naval_sam) is fired to intercept the
red_mrbm_1(s) to save Washington.

The top startup file to run is "ballistic_shootdown.txt".
This is a one on one example.

The "many_ballistic_shootdown.txt" is another top startup file
that depicts a nine against nine shootdown by only changing out
the scenario files. Take note that there are nine launchers for the red_mrbm_1's
and only six for the blue_naval_sam's.  One of the launchers has more than one weapon.

The command "show_graphics" provides output for Mystic concerning
the interceptor evaluation criteria on the ballistic path of what is being
evaluated to be shot down.  (The show_graphics subcommand is located within the
WSF_GUIDANCE_COMPUTER block on the weapon.)
*  An orange dot is created at the time of evaluation.
*  A green dot is displayed at the target location when the interceptor will launch.
*  A red dot at the point of possible intercepts
*  A white dot shows the last possible intercept location.
*  A yellow dot shows the final location of the weapon intercept.

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
