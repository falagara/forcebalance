""" @package gmxio GROMACS input/output.

@todo Even more stuff from forcefield.py needs to go into here.

@author Lee-Ping Wang
@date 12/2011
"""

import os
from re import match, sub
from nifty import isint
from numpy import array
from basereader import BaseReader
from subprocess import Popen, PIPE
from forceenergymatch import ForceEnergyMatch

## VdW interaction function types
nftypes = [None, 'VDW', 'VDW_BHAM']
## Pairwise interaction function types
pftypes = [None, 'VPAIR', 'VPAIR_BHAM']
## Bonded interaction function types
bftypes = [None, 'BONDS', 'G96BONDS', 'MORSE']
## Angle interaction function types
aftypes = [None, 'ANGLES', 'G96ANGLES', 'CROSS_BOND_BOND',
           'CROSS_BOND_ANGLE', 'UREY_BRADLEY', 'QANGLES']
## Dihedral interaction function types
dftypes = [None, 'PDIHS', 'IDIHS', 'RBDIHS']

## Section -> Interaction type dictionary.
## Based on the section you're in
## and the integer given on the current line, this looks up the
## 'interaction type' - for example, within bonded interactions
## there are four interaction types: harmonic, G96, Morse, and quartic
## interactions.
fdict = {
    'atomtypes'     : nftypes,
    'nonbond_params': pftypes,
    'bonds'         : bftypes,
    'bondtypes'     : bftypes,
    'angles'        : aftypes,
    'angletypes'    : aftypes,
    'dihedrals'     : dftypes,
    'dihedraltypes' : dftypes,
    'virtual_sites2': ['NONE','VSITE2'],
    'virtual_sites3': ['NONE','VSITE3','VSITE3FD','VSITE3FAD','VSITE3OUT'],
    'virtual_sites4': ['NONE','VSITE4FD']
    }

## Interaction type -> Parameter Dictionary.
## A list of supported GROMACS interaction types in force matching.
## The keys in this dictionary (e.g. 'BONDS','ANGLES') are values
## in the interaction type dictionary.  As the program loops through
## the force field file, it first looks up the interaction types in
## 'fdict' and then goes here to do the parameter lookup by field.
## @todo This needs to become more flexible because the parameter isn't
## always in the same field.  Still need to figure out how to do this.
## @todo How about making the PDIHS less ugly?
pdict = {'BONDS':{3:'B', 4:'K'},
         'G96BONDS':{},
         'MORSE':{3:'B', 4:'C', 5:'E'},
         'ANGLES':{4:'B', 5:'K'},
         'G96ANGLES':{},
         'CROSS_BOND_BOND':{4:'1', 5:'2', 6:'K'},
         'CROSS_BOND_ANGLE':{4:'1', 5:'2', 6:'3', 7:'K'},
         'QANGLES':{4:'B', 5:'K0', 6:'K1', 7:'K2', 8:'K3', 9:'K4'},
         'UREY_BRADLEY':{4:'T', 5:'K1', 6:'B', 7:'K2'},
         'PDIHS1':{5:'B', 6:'K'},
         'PDIHS2':{5:'B', 6:'K'},
         'PDIHS3':{5:'B', 6:'K'},
         'PDIHS4':{5:'B', 6:'K'},
         'PDIHS5':{5:'B', 6:'K'},
         'PDIHS6':{5:'B', 6:'K'},
         'IDIHS':{5:'B', 6:'K'},
         'VDW':{4:'S', 5:'T'},
         'VPAIR':{3:'S', 4:'T'},
         'COUL':{6:''},
         'RBDIHS':{6:'K1', 7:'K2', 8:'K3', 9:'K4', 10:'K5'},
         'VDW_BHAM':{4:'A', 5:'B', 6:'C'},
         'VPAIR_BHAM':{3:'A', 4:'B', 5:'C'},
         'QTPIE':{1:'C', 2:'H', 3:'A'},
         'VSITE2':{4:'A'},
         'VSITE3':{5:'A',6:'B'},
         'VSITE3FD':{5:'A',6:'D'},
         'VSITE3FAD':{5:'T',6:'D'},
         'VSITE3OUT':{5:'A',6:'B',7:'C'},
         'VSITE4FD':{6:'A',7:'B',8:'D'},
         }

def parse_atomtype_line(line):
    """ Parses the 'atomtype' line.
    
    Parses lines like this:\n
    <tt> opls_135     CT    6   12.0107    0.0000    A    3.5000e-01    2.7614e-01\n
    C       12.0107    0.0000    A    3.7500e-01    4.3932e-01\n
    Na  11    22.9897    0.0000    A    6.068128070229e+03  2.662662556402e+01  0.0000e+00 ; PARM 5 6\n </tt>
    Look at all the variety!

    @param[in] line Input line.
    @return answer Dictionary containing:\n
    atom type\n
    bonded atom type (if any)\n
    atomic number (if any)\n
    atomic mass\n
    charge\n
    particle type\n
    force field parameters\n
    number of optional fields
    """
    # First split the line up to the comment.  We don't care about the comment at this time
    sline = line.split(';')[0].split()
    # The line must contain at least six fields to be considered data.
    if len(sline) < 6:
        return
    # Using variable "wrd" because the line has a variable number of fields
    # Can you think of a better way?
    wrd = 0
    bonus = 0
    atomtype = sline[wrd]
    batomtype = sline[wrd]
    wrd += 1
    # The bonded atom type, a pecularity of OPLS-AA
    # Test if it begins with a letter.  Seems to work. :)
    if match('[A-Za-z]',sline[wrd]):
        batomtype = sline[wrd]
        wrd += 1
        bonus += 1
    # Now to test if the next line is an atomic number or a mass.
    # Atomic numbers never have decimals...
    atomicnum = -1
    if isint(sline[wrd]):
        atomicnum = int(sline[wrd])
        wrd += 1
        bonus += 1
    # The mass can be overridden in the 'atoms' section.
    mass = float(sline[wrd])
    wrd += 1
    # Atom types have a default charge though this is almost always overridden
    chg  = float(sline[wrd])
    wrd += 1
    # Particle type. Actual atom or virtual site?
    ptp  = sline[wrd]
    wrd += 1
    param = [float(i) for i in sline[wrd:]]
    answer = {'atomtype':atomtype, 'batomtype':batomtype, 'atomicnum':atomicnum, 'mass':mass, 'chg':chg, 'ptp':ptp, 'param':param, 'bonus':bonus}
    return answer

class ITP_Reader(BaseReader):

    """Finite state machine for parsing GROMACS force field files.
    
    We open the force field file and read all of its lines.  As we loop
    through the force field file, we look for two types of tags: (1) section
    markers, in GMX indicated by [ section_name ], which allows us to determine
    the section, and (2) parameter tags, indicated by the 'PARM' or 'RPT' keywords.
    
    As we go through the file, we figure out the atoms involved in the interaction
    described on each line.
    
    When a 'PARM' keyword is indicated, it is followed by a number which is the field
    in the line to be modified, starting with zero.  Based on the field number and the
    section name, we can figure out the parameter type.  With the parameter type
    and the atoms in hand, we construct a 'parameter identifier' or pid which uniquely
    identifies that parameter.  We also store the physical parameter value in an array
    called 'pvals0' and the precise location of that parameter (by filename, line number,
    and field number) in a list called 'pfields'.
    
    An example: Suppose in 'my_ff.itp' I encounter the following on lines 146 and 147:
    
    @code
    [ angletypes ]
    CA   CB   O   1   109.47  350.00  ; PARM 4 5
    @endcode
    
    From reading <tt>[ angletypes ]</tt> I know I'm in the 'angletypes' section.
    
    On the next line, I notice two parameters on fields 4 and 5.
    
    From the atom types, section type and field number I know the parameter IDs are <tt>'ANGLESBCACBO'</tt> and <tt>'ANGLESKCACBO'</tt>.
    
    After building <tt>map={'ANGLESBCACBO':1,'ANGLESKCACBO':2}</tt>, I store the values in
    an array: <tt>pvals0=array([109.47,350.00])</tt>, and I put the parameter locations in
    pfields: <tt>pfields=[['my_ff.itp',147,4,1.0],['my_ff.itp',146,5,1.0]]</tt>.  The 1.0
    is a 'multiplier' and I will explain it below.
    
    Note that in the creation of parameter IDs, we run into the issue that the atoms
    involved in the interaction may be labeled in reverse order (e.g. <tt>OCACB</tt>).  Thus,
    we store both the normal and the reversed parameter ID in the map.
    
    Parameter repetition and multiplier:
    
    If <tt>'RPT'</tt> is encountered in the line, it is always in the syntax:
    <tt>'RPT 4 ANGLESBCACAH 5 MINUS_ANGLESKCACAH /RPT'</tt>.  In this case, field 4 is replaced by
    the stored parameter value corresponding to <tt>ANGLESBCACAH</tt> and field 5 is replaced by
    -1 times the stored value of <tt>ANGLESKCACAH</tt>.  Now I just picked this as an example,
    I don't think people actually want a negative angle force constant .. :) the <tt>MINUS</tt>
    keyword does come in handy for assigning atomic charges and virtual site positions.
    In order to achieve this, a multiplier of -1.0 is stored into pfields instead of 1.0.
    
    @todo Note that I can also create the opposite virtual site position by changing the atom
    labeling, woo!
    
    """
    
    def __init__(self,fnm):
        # Initialize the superclass. :)
        super(ITP_Reader,self).__init__(fnm)
        ## The current section that we're in
        self.sec = None
        ## Nonbonded type
        self.nbtype = None
        ## The current residue (set by the moleculetype keyword)
        self.res    = None
        ## The mapping of (this residue, atom number) to (atom name) for building atom-specific interactions in [ bonds ], [ angles ] etc.
        self.adict  = {}
        ## The parameter dictionary (defined in this file)
        self.pdict  = pdict

    def feed(self, line):
        """ Given a line, determine the interaction type and the atoms involved (the suffix).
        
        For example, we want \n
        <tt> H    O    H    5    1.231258497536e+02    4.269161426840e+02   -1.033397697685e-02   1.304674117410e+04 ; PARM 4 5 6 7 </tt> \n
        to give us itype = 'UREY_BRADLEY' and suffix = 'HOH'
        
        If we are in a TypeSection, it returns a list of atom types; \n
        If we are in a TopolSection, it returns a list of atom names.
        
        The section is essentially a case statement that picks out the
        appropriate interaction type and makes a list of the atoms
        involved

        Note that we can call gmxdump for this as well, but I
        prefer to read the force field file directly.
        
        ToDo: [ atoms ] section might need to be more flexible to accommodate optional fields
        
        """
        s          = line.split()
        atom       = []
        self.itype = None
        self.ln   += 1
        # No sense in doing anything for an empty line or a comment line.
        if len(s) == 0 or match('^;',line): return None, None
        # Now go through all the cases.
        if match('^\[.*\]',line):
            # Makes a word like "atoms", "bonds" etc.
            self.sec = sub('[\[\] \n]','',line)
        elif self.sec == 'defaults':
            self.nbtype = int(s[0])
        elif self.sec == 'moleculetype':
            self.res    = s[0]
        elif self.sec == 'atomtypes':
            atype = parse_atomtype_line(line)
            # Basically we're shifting the word positions
            # based on the syntax of the line in 'atomtype', but it allows the parameter typing to
            # keep up with the flexibility of the syntax of these lines.
            if atype['bonus'] > 0:
                pdict['VDW'] = {4+atype['bonus']:'S',5+atype['bonus']:'T'}
                pdict['VDW_BHAM'] = {4+atype['bonus']:'A', 5+atype['bonus']:'B', 6+atype['bonus']:'C'}
            atom = atype['atomtype']
            self.itype = fdict[self.sec][self.nbtype]
        elif self.sec == 'nonbond_params':
            atom = [s[0], s[1]]
            self.itype = pftypes[self.nbtype]
        elif self.sec == 'atoms':
            atom = [s[4]]
            self.itype = 'COUL'
            # Build the adict here.
            self.adict.setdefault(s[3],[]).append(s[4])
        elif self.sec == 'qtpie':
            # The atom involved is labeled by the atomic number.
            atom = [s[0]]
            self.itype = 'QTPIE'
        elif self.sec == 'bonds':
            atom = [self.adict[self.res][int(i) - 1] for i in s[:2]]
            self.itype = fdict[self.sec][int(s[2])]
        elif self.sec == 'bondtypes':
            atom = [s[0], s[1]]
            self.itype = fdict[self.sec][int(s[2])]
        elif self.sec == 'angles':
            atom = [self.adict[self.res][int(i) - 1] for i in s[:3]]
            self.itype = fdict[self.sec][int(s[3])]
        elif self.sec == 'angletypes':
            atom = [s[0], s[1], s[2]]
            self.itype = fdict[self.sec][int(s[3])]
        elif self.sec == 'dihedrals':
            atom = [self.adict[self.res][int(i)-1] for i in s[:4]]
            self.itype = fdict[self.sec][int(s[4])]
            if self.itype == 'PDIHS' and len(s) >= 7:
                # Add the multiplicity of the dihedrals to the interaction type.
                self.itype += s[7]
        elif self.sec == 'dihedraltypes':
            atom = [s[0], s[1], s[2], s[3]]
            self.itype = fdict[self.sec][int(s[4])]
            if self.itype == 'PDIHS' and len(s) >= 7:
                self.itype += s[7]
        elif self.sec == 'virtual_sites2':
            atom = [s[0]]
            self.itype = fdict[self.sec][int(s[3])]
        elif self.sec == 'virtual_sites3':
            atom = [s[0]]
            self.itype = fdict[self.sec][int(s[4])]
        elif self.sec == 'virtual_sites4':
            atom = [s[0]]
            self.itype = fdict[self.sec][int(s[5])]
        else:
            return [],"Confused"
        if len(atom) > 1 and atom[0] > atom[-1]:
            # Enforce a canonical ordering of the atom labels in a parameter ID
            atom = atom[::-1]
        self.suffix = ''.join(atom)

def gmxx2_print(fnm, vec, type):
    """ Prints a vector to a file to feed it to the modified GROMACS.
    Ported over from the old version so it is a bit archaic for my current taste.

    @param[in] fnm The file name that we're printing the data to
    @param[in] vec 1-D array of data
    @param[in] type Either 'int' or 'double', indicating the type of data.
    """
    fobj = open(fnm, 'w')
    vec = array(vec)
    print >> fobj, vec.shape[0],
    if type == "int":
        for i in vec:
            print >> fobj, i,
    elif type == "double":
        for i in vec:
            print >> fobj, "% .12e" % i,
    fobj.close()

def rm_gmx_baks(dir):
    # Delete the #-prepended files that GROMACS likes to make
    for root, dirs, files in os.walk(dir):
        for file in files:
            if match('^#',file):
                os.remove(file)

class ForceEnergyMatch_GMX(ForceEnergyMatch):
    """ Subclass of FittingSimulation for force and energy matching using normal GROMACS.
    Implements the prepare_temp_directory and energy_force_driver methods."""

    def __init__(self,options,sim_opts,forcefield):
        ## Name of the trajectory, we need this BEFORE initializing the SuperClass
        self.trajfnm = "all.gro"
        ## Initialize the SuperClass!
        super(ForceEnergyMatch_GMX,self).__init__(options,sim_opts,forcefield)
    
    def prepare_temp_directory(self, options, sim_opts):
        os.environ["GMX_NO_SOLV_OPT"] = "TRUE"
        abstempdir = os.path.join(self.root,self.tempdir)
        # Link the necessary programs into the temporary directory
        os.symlink(os.path.join(options['gmxpath'],"mdrun"+options['gmxsuffix']),os.path.join(abstempdir,"mdrun"))
        os.symlink(os.path.join(options['gmxpath'],"grompp"+options['gmxsuffix']),os.path.join(abstempdir,"grompp"))
        os.symlink(os.path.join(options['gmxpath'],"g_energy"+options['gmxsuffix']),os.path.join(abstempdir,"g_energy"))
        os.symlink(os.path.join(options['gmxpath'],"g_traj"+options['gmxsuffix']),os.path.join(abstempdir,"g_traj"))
        # Link the run files
        os.symlink(os.path.join(self.root,self.simdir,"shot.mdp"),os.path.join(abstempdir,"shot.mdp"))
        os.symlink(os.path.join(self.root,self.simdir,"topol.top"),os.path.join(abstempdir,"topol.top"))
        # Write the trajectory to the temp-directory
        self.traj.write(os.path.join(abstempdir,"all.gro"),subset=range(self.ns))
        # Print out the first conformation in all.gro to use as conf.gro
        self.traj.write(os.path.join(abstempdir,"conf.gro"),subset=[0])

    def energy_force_driver(self, shot):
        """ Computes the energy and force using GROMACS for a single
        snapshot.  This does not require GROMACS-X2. """

        # Remove backup files.
        rm_gmx_baks(os.getcwd())
        # Write the correct conformation.
        self.traj.write('conf.gro',subset=[shot])
        # Call grompp followed by mdrun.
        o, e = Popen(["./grompp", "-f", "shot.mdp"],stdout=PIPE,stderr=PIPE).communicate()
        o, e = Popen(["./mdrun", "-o", "shot.trr", "-rerunvsite"], stdout=PIPE, stderr=PIPE).communicate()
        # Gather information
        o, e = Popen(["./g_energy","-xvg","no"],stdin=PIPE,stdout=PIPE,stderr=PIPE).communicate('Potential')
        o, e = Popen(["./g_traj","-xvg","no","-f","shot.trr","-of","force.xvg","-fp"],stdin=PIPE,stdout=PIPE,stderr=PIPE).communicate('System')
        E = [float(open("energy.xvg").readlines()[0].split()[1])]
        F = [float(i) for i in open("force.xvg").readlines()[0].split()[1:] if float(i) != 0.0]
        M = array(E + F)
        return M

    def energy_force_driver_all(self):
        """ Computes the energy and force using GROMACS for a trajectory.  This does not require GROMACS-X2. """
        # Remove backup files.
        rm_gmx_baks(os.getcwd())
        # Call grompp followed by mdrun.
        o, e = Popen(["./grompp", "-f", "shot.mdp"],stdout=PIPE,stderr=PIPE).communicate()
        o, e = Popen(["./mdrun", "-o", "shot.trr", "-rerunvsite", "-rerun", "all.gro"], stdout=PIPE, stderr=PIPE).communicate()
        # Gather information
        o, e = Popen(["./g_energy","-xvg","no"],stdin=PIPE,stdout=PIPE,stderr=PIPE).communicate('Potential')
        o, e = Popen(["./g_traj","-xvg","no","-f","shot.trr","-of","force.xvg","-fp"],stdin=PIPE,stdout=PIPE,stderr=PIPE).communicate('System')
        M = []
        Efile = open("energy.xvg").readlines()
        Ffile = open("force.xvg").readlines()
        # Loop through the snapshots
        for Eline, Fline in zip(Efile, Ffile):
            # Compute the potential energy and append to list
            Energy = [float(Eline.split()[1])]
            Force = [float(i) for i in Fline.split()[1:] if float(i) != 0.0]
            M.append(array(Energy + Force))
        return M
