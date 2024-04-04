from rich.live import Live
from rich.table import Table
from rich.spinner import Spinner
import asyncio
from enum import Enum
from types import SimpleNamespace

def output_grid( rows ):
    grid = Table.grid( padding=(0,1), collapse_padding=True )
    grid.vertical = "bottom"
    for kwargs in ({"width":1},{},{"justify":"center"},{}):
        grid.add_column( **kwargs )
    for row in rows:
        row.append_to_grid( grid )
    return grid

def status_cells( style, word ):
    return ( "[{}][".format( style ),
             "[{}]{}".format( style, word ),
             "[{}]]".format( style )
            )

class States(Enum):
    skipped = status_cells( "bright_black", "Sprunget over" )
    texing = status_cells( "blue", "TeX'er" )
    collating = status_cells( "blue", "Samler" )
    success = status_cells( "green", "OK" )
    errors = status_cells( "orange3", "Havde fejl" )
    failed = status_cells( "red", "Mislykkedes" )
    setup = status_cells( "bright_black", "Forbereder" )

processing_states = (States.texing, States.collating)

# TODO: Better names, for heck’s sake!

class OutputRow:
    rate_multiplier = .25
    max_rate = 6 * rate_multiplier
    
    def __init__( self, all_rows, state, live = None, name="", rate=0 ):
        self.live = live
        self.spinner = Spinner( "dots" )
        self.spinner.speed = rate * self.rate_multiplier
        self.next_speed = 0
        self.all_rows = all_rows
        self._name = name
        self._state = state

        try:
            self.renew_row()
        except AttributeError as er:
            if self.live == None:
                # become a dummy
                self.live = SimpleNamespace( update = lambda *_: None )
                self.renew_row = lambda *_: None
                self.append_to_grid = lambda *_: None
                self.activity_ping = lambda *_: None
                self.rate_update = lambda *_: None
            else:
                raise er
        # else:
        #     asyncio.run( self.spinner_brake() )

    @classmethod
    def set_live( live ):
        OutputRow.live = live

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, value):
        self._state = value
        self.renew_row()

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, name):
        self._name = name
        self.renew_row()

    def renew_row(self):
        self.row = self.spinner if self.state in processing_states else " "\
            , *self.state.value \
            , self.name
        self.live.update( output_grid( self.all_rows ))

    def append_to_grid( self, grid ):
        grid.add_row( *self.row )

    def activity_ping( self ):
        self.spinner.speed = \
            min( self.max_rate, self.spinner.speed + self.rate_multiplier )
        self.next_speed = \
            min( self.max_rate, self.next_speed + self.rate_multiplier )

    def rate_update( self ):
        self.spinner.speed = self.next_speed
        self.next_speed = 0

    async def spinner_brake( self ):
        while True:
            await asyncio.sleep( 1 )
            self.rate_update()

class GridManager:              # not that kind of manager
    def __init__(self, *args, **kwargs):
        self.live = Live( output_grid( [] ), *args, **kwargs)
        self.live.start()
        self.rows = []

    def new_row_number( self, state, name="", rate=0 ):
        number = len( self.rows )
        self.rows += [ OutputRow( self.rows, state, name=name, rate=rate, live=self.live ) ]
        self.live.update( output_grid( self.rows ) )
        print("ping", self.rows )
        return number

    def state_for_number( self, number, state ):
        self.rows[ number ].state = state

    def text_for_number( self, number, text ):
        self.rows[ number ].name = text

    def activity_ping_number( self, number ):
        self.rows[ number ].activity_ping()
