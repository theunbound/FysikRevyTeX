from base_classes import Role
from helpers import rows_from_csv_etc
from itertools import pairwise

test_file = "E:/thebe/Downloads/Rollefordeling - Roller.tsv"

rows = rows_from_csv_etc( test_file )
abbr_row = 1
name_row = 2

name_cols = [ i for i,v in enumerate( rows[0] ) if v ]
matrix_start_row = [ v[0] != "" for v in rows ].index(True)
matrix_end_col = [ all( rows[r][c] != ""
                        for r in range( 1, matrix_start_row - 1 )
                       )
                   for c in range( name_cols[0], len( rows[0] ) )
                  ].index(False) \
                  + name_cols[0]

def botch_mat_dict():
    return { rows[0][ start_col ]:
             { "roles": [
                 Role( rows[abbr_row][col],
                       rows[ [ rows[r][col] != ""
                               for r in range( matrix_start_row,
                                               len( rows ) - 1 )
                              ].index(True) + matrix_start_row ][0],
                       rows[name_row][col]
                      ) for col in range( start_col, end_col )
             ] }
             for start_col, end_col
             in pairwise( name_cols + [ matrix_end_col ] )
            }

