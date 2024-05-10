# builtins
from functools import reduce
from itertools import zip_longest
from pathlib import Path

# dependencies
from fuzzywuzzy import fuzz

# locals
from base_classes import Role
from classy_revy import Material
from helpers import rows_from_csv_etc

def trim_end( ar ):
    return reduce(
        lambda a,e: [e] + a if a or e else a,
        reversed( ar ),
        []
    )

def rowwise_csv( fn, revue ):
    """Det her er formatet, som create.py laver, når det får
argumentet roles-sheet. Men med den forskel, at overskrift-kolonnen er
valgfri. Rækkerne med ordantal bliver ignoreret, og behøver ikke at
være der. Kolonnen med aktnavne ignoreres, og behøver ikke at
udfyldes. For hvert nummer kan filnavn eller titel udelades. Hvis
begge er angivet prioriteres filnavnet.

    """

    materials = [ material for act in revue.acts for material in act.materials ]
    
    scorechart = {}
    translations = {}

    rows = rows_from_csv_etc( fn )
    row_gen = ( row for row in rows )
    title_col = 1 if\
        len( [ True for row in rows if not row[0] == '' ] ) / len( rows )\
        > 0.5 else 0

    def gather_mat( info_row ):
        title = info_row[ title_col + 1 ]
        fn = info_row[ title_col + 2 ]
        abbrs = trim_end( info_row[ title_col + 3 : ] )

        actor_row = next( row_gen )
        if any( actor_row[ title_col + 1 : title_col + 2 ] ):
            return gather_mat( actor_row )
        actors = trim_end( actor_row[ title_col + 3 : ] )

        desc_row = next( row_gen )
        if any( desc_row[ title_col + 1 : title_col + 2 ] ):
            return gather_mat( desc_row )
        descs = trim_end( desc_row[ title_col + 3 : ] )

        roles = [ Role( abbr, actor, desc )
                  for abbr, actor, desc in zip_longest( abbrs, actors, descs,
                                                        fillvalue="" )
                 ]
        
        if fn:
            translations[ title or fn ] = {
                "material": next(
                    ( mat for mat in materials
                      if Path( mat.path ).resolve() == Path( fn ).resolve()
                     ),
                    Material.fromfile( fn )
                ),
                "conf": "fn",   # or some actual signal...
                "roles": roles
            }
        else:
            scorechart[ title ] = {
                "scores": [ fuzz.partial_ratio( mat.title, title )
                            for mat in materials ],
                "roels": roles
            }

    try:
        while True:
            row = next( row_gen )
            if any( row[ title_col + 1 : title_col + 2 ] ):
                gather_mat( row )
    except StopIteration:
        pass

    fn_mats_indices = [ materials.index( translations[ title ][ "material" ] )
                        for title in translations ]
    for title in scorechart:
        for i in fn_mats_indices:
            scorechart[ title ][ "scores" ][ i ] = 0

    return { "translations": translations, "scorechart": scorechart }
