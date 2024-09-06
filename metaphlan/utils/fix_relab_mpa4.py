#!/usr/bin/env python
__author__ = ('Aitor Blanco Miguez (aitor.blancomiguez@unitn.it), '
              'Claudia Mengoni (claudia.mengoni@unitn.it)')
__version__ = '4.1.1'
__date__ = '11 Mar 2024'

import os, time
try:
    from .util_fun import info, error, warning, openrt
except ImportError:
    from util_fun import info, error, warning, openrt
import argparse as ap
import numpy as np

script_install_folder = os.path.dirname(os.path.abspath(__file__))
OCT22_FIXES = os.path.join(script_install_folder, 'oct22_fix_tax.tsv')

def read_params():
    """ Reads and parses the command line arguments of the script

    Returns:
        namespace: The populated namespace with the command line arguments
    """
    p = ap.ArgumentParser(formatter_class=ap.RawTextHelpFormatter, add_help=False, 
                          description="\nThis script allows you to fix some taxonomic inconsistencies "
                                      "present in mpa_vOct22_CHOCOPhlAnSGB_202212 and mpa_vJun23_CHOCOPhlAnSGB_202307.\n" +
                                      "The output profile will have fixed taxonomies and renormalized relative abundances.\n")
    
    requiredNamed = p.add_argument_group('required arguments')
    requiredNamed.add_argument('-i', '--input', type=str, default=None, help="The path to the input profile")
    requiredNamed.add_argument('-o', '--output', type=str, default=None, help="The path to the output profile")
    p.add_argument('--merged_profiles', action='store_true', default=False, help=("To specify when running the script on profiles that were already merged with merge_metaphlan_tables.py"))
    p.add_argument("-h", "--help", action="help", help="show this help message and exit")

    return p.parse_args()

def read_oct22_fixes(file):
    """Reads the tab separated file with old and new taxonomies of Oct22
    Args:
        file: file with Oct22 fixes
    """
    oct_fixes = dict()
    with open(file) as inf:
        for l in inf.readlines()[1:]:
            old_tax, new_tax, new_tax_id = l.split('\t')
            oct_fixes[old_tax] = (new_tax, new_tax_id.strip())
    return oct_fixes

def check_params(args):
    """Checks the mandatory command line arguments of the script

    Args:
        args (namespace): the arguments to check
    """
    if not args.input:
        error('--input must be specified', exit=True)
    elif not os.path.exists(args.input):
        error(f'The file {args.input} does not exist', exit=True)
    if not args.output:
        error('--output must be specified', exit=True)

def assign_higher_taxonomic_levels(taxa_levs, merged):
    """Aggregates taxa at lower levels (e.g., species) to higher levels (e.g., genus)"""
    if not merged:
        for i in range(1, 8):
            j = i + 1
            for ss in taxa_levs[-i]:
                # Parse the taxonomy by splitting on '|'
                taxonomy_parts = ss.split('|')
                gg = '|'.join(taxonomy_parts[:-1])  # Higher level taxon
                
                # Get the name of the higher taxonomic level from the lower one
                gg_n = '|'.join(taxa_levs[-i][ss][0].split('|')[:-1])
                
                # If the higher taxon doesn't exist, initialize it
                if gg not in taxa_levs[-j]:
                    taxa_levs[-j][gg] = [gg_n, taxa_levs[-i][ss][1], '']
                else:
                    # Accumulate the relative abundance at the higher level
                    taxa_levs[-j][gg][1] += taxa_levs[-i][ss][1]
    else:
        # For merged profiles (multiple columns), handle as arrays
        for i in range(1, 8):
            j = i + 1
            for ss in taxa_levs[-i]:
                taxonomy_parts = ss.split('|')
                gg = '|'.join(taxonomy_parts[:-1])  # Higher level taxon
                
                if gg not in taxa_levs[-j]:
                    taxa_levs[-j][gg] = taxa_levs[-i][ss]
                else:
                    # Accumulate the relative abundance for each column
                    taxa_levs[-j][gg] = np.add(taxa_levs[-j][gg], taxa_levs[-i][ss])
    
    return taxa_levs

def fix_relab_mpa4(input, output, merged):
    """Fixes taxonomic inconsistencies and renormalizes the relative abundances"""
    taxa_levs = [{}, {}, {}, {}, {}, {}, {}, {}] 
    release = None
    unclassified_fraction = 0
    with openrt(input) as rf:
        with open(output, 'w') as wf:
            for line in rf:
                if line.startswith('#mpa_v'):
                    release = line.strip()[1:]
                    line = '_'.join(line.split('_')[:-1])
                    wf.write('{}_202403\n'.format(line.strip()))
                elif line.startswith('#') or line.startswith('clade_name'):
                    wf.write(line)
                elif line.startswith('UNCLASSIFIED'):
                    wf.write(line)
                    line = line.split('\t')
                    if not merged:
                        unclassified_fraction = float(line[2])
                    else:
                        unclassified_fraction = [float(l) for l in line[1:]]
                else:
                    if 't__' in line:
                        if release == 'mpa_vJun23_CHOCOPhlAnSGB_202307':
                            if 'p__Bacillota' in line:
                                line = line.replace('p__Bacillota', 'p__Firmicutes')
                            elif 'f__Saccharomycetales_unclassified' in line:
                                line = line.replace('f__Saccharomycetales_unclassified', 'f__Debaryomycetaceae')
                            line = line.strip().split('\t') 
                        elif release == 'mpa_vOct22_CHOCOPhlAnSGB_202212':
                            line = line.strip().split('\t')
                            if line[0] in oct_fixes:
                                if not merged:
                                    line[0], line[1] = oct_fixes[line[0]]
                                else:
                                    line[0] = oct_fixes[line[0]][0]
                        else:
                            error('The release is not specified in the header or does not correspond to mpa_vJun23_CHOCOPhlAnSGB_202307 or mpa_vOct22_CHOCOPhlAnSGB_202212', exit=True)
                        
                        if not merged:           
                            taxa_levs[-1][line[0]] = [line[1], float(line[2]), line[3] if len(line) == 4 else '']
                        else:
                            taxa_levs[-1][line[0]] = [float(l) for l in line[1:]]
                            ncols = len(line) - 1

            taxa_levs = assign_higher_taxonomic_levels(taxa_levs, merged)

            # normalize the relative abundances and write to file
            if not merged:
                sum_level = dict()
                for level in range(len(taxa_levs)):
                    sum_level[level] = 0
                    for tax in taxa_levs[level]:
                        sum_level[level] += taxa_levs[level][tax][1]
                
                # Ensure that the unclassified fraction is part of the total sum
                for level in range(len(taxa_levs)):
                    total_sum = sum_level[level] + unclassified_fraction
                    for tax in taxa_levs[level]:
                        taxa_levs[level][tax][1] = round((100) * taxa_levs[level][tax][1] / total_sum, 5)
                        wf.write(tax + '\t' + '\t'.join([str(x) for x in taxa_levs[level][tax]]) + '\n')
                    
                    # Debug: print the sum including unclassified_fraction
                    print(f"Level {level} total sum including unclassified: {total_sum}")

            else:
                if unclassified_fraction == 0:
                    unclassified_fraction = [0] * ncols
                sum_level = dict()
                for level in range(len(taxa_levs)):
                    sum_level[level] = [0] * ncols
                    for tax in taxa_levs[level]:
                        sum_level[level] = np.add(sum_level[level], taxa_levs[level][tax])

                # Normalize merged profiles, adjusting each column
                for level in range(len(taxa_levs)):
                    for tax in taxa_levs[level]:
                        for n in range(len(taxa_levs[level][tax])):
                            total_sum = sum_level[level][n] + unclassified_fraction[n]
                            taxa_levs[level][tax][n] = round((100) * taxa_levs[level][tax][n] / total_sum, 5)
                        wf.write(tax + '\t' + '\t'.join([str(x) for x in taxa_levs[level][tax]]) + '\n')
                    
                    # Debug: print the sum for each level
                    print(f"Level {level} total sum per column: {sum_level[level]} including unclassified: {unclassified_fraction}")

def main():
    global oct_fixes
    t0 = time.time()
    args = read_params()
    info("Start fixing profile")
    check_params(args)
    oct_fixes = read_oct22_fixes(OCT22_FIXES) 
    fix_relab_mpa4(args.input, args.output, args.merged_profiles)
    exec_time = time.time() - t0
    info("Finish fixing profile ({} seconds)".format(round(exec_time, 2)))


if __name__ == '__main__':
    main()
