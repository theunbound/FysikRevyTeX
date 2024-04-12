from helpers import rows_from_csv_etc

def rowwise_csv( fn ):
    """Det her er formatet, som create.py laver, når det får argumentet
roles_sheet. Men med den forskel, at overskrift-cellerne, både i
første række og kolonne er valgfri, rækkerne med ordantal bliver
ignoreret, og behøver ikke at være der. Kolonnen med aktnavne
ignoreres, og behøver ikke at være der. Enten filnavne eller titler
kan udelades, eller byttes rundt, og vi prøver at finde ud af det
alligevel.

    """

    rows = rows_from_csv_etc( fn )
    title_col = 1 if\
        len( [ True for row in rows if not row[0] == '' ] ) / len( rows )\
        > 0.5 else 0

    mats = [[]]
    for row in rows:
        if len( mats[0] ) == 0:
            mats[0] = row
            continue
        if 
