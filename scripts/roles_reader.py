from helpers import rows_from_csv_etc

def rowwise_csv( fn ):
    """Det her er formatet, som create.py laver, når det får
argumentet roles-sheet. Men med den forskel, at overskrift-kolonnen er
valgfri. Rækkerne med ordantal bliver ignoreret, og behøver ikke at
være der. Kolonnen med aktnavne ignoreres, og behøver ikke at
udfyldes. For hvert nummer kan filnavn eller titel udelades. Hvis
begge er angivet prioriteres filnavnet.

    """

    translations = {}

    rows = rows_from_csv_etc( fn )
    row_gen = row for row in rows
    title_col = 1 if\
        len( [ True for row in rows if not row[0] == '' ] ) / len( rows )\
        > 0.5 else 0

    def gather_mat( info_row ):
        title = info_row[ title_col + 1 ]
        fn = info_row[ title_col + 2 ]
        abbr = info_row[ title_col + 3 : ]

        actor_row = next( row_gen )
        if any( [ title_col + 1 : title_col + 2 ] ):
            return gather_mat( actor_row )
        actors = actor_row[ title_col + 3 : ]

        desc_row = next( row_gen )
        if any( [ title_col + 1 : title_col + 2 ] ):
            return gather_mat( desc_row )
        descs = desc_row[ title_col + 3 : ]

        

    mats = [[]]
    for row in rows:
        if len( mats[0] ) == 0:
            mats[0] = row
            continue
        if 
