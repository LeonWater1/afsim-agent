**CUI**

# aea_iads demo

This directory contains the necessary files to test the EW effects
in a scenario similar to the iads_demo baseline scenario.

The SOJ and EW_Radar have EA and EP techniques, respectively, with them
to aid in the testing and verification of these techniques.

The strike.txt file is the normal input file to run the simulation
as a single application. The replay file will be written to the
output directory.

Also included are two realtime run files strike-rt.txt and iads-rt.txt
that can be run concurrently to test the jamming and EW effects over DIS.
Each WSF application communicates over DIS. The applications can be run
on separate hosts or on the same host.  The file dis_data.txt provides
the DIS Enumeration mapping for the entity types, emitter types, and ew
technique types.

To visually monitor the progress of the realtime simulations, Warlock can
be opened and then configured to monitor multicast address 224.2.25.55, 
port 3225 via an input file containing a dis_interface block.

## CUI Designation Indicator
* Controlled by: Air Force Research Laboratory
* Controlled by: Aerospace Systems Directorate
* CUI Categories: CTI, EXPT
* LDC/Distribution Statement: DIST-C
* POC: afrl.rq.afsim@us.af.mil

## Notices and Warnings

### DISTRIBUTION STATEMENT C
Distribution authorized to US Government agencies and their contractors;
Critical Technology, Export Controlled; (2021 Oct 06). Other requests for this
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
