# coding: utf-8
from itertools import dropwhile
from datetime import timedelta

from config import configuration as conf

def write_template( revue ):
   # will throw FileExistError if, well, you know...
   with open( conf["Files"]["timesheet-info"], "x" ) as f:
      f.write("""
# some instructions

""")
      for act in revue.acts:
         f.write( act.name.replace('"','') + "\n" )
         for mat in act.materials:
            f.write( '"{}";\n'.format( mat.title.replace('"','') ) )
            f.write( "-;dur=1:00;\n\n" )

class Entry:
   copy_attrs = [ "dur" ]
   def __init__(self, line=None, *, dur=None, name=None):
      self.children = []
      self.dur = dur
      self.name = name
      
      if line:
         name_around = '"'.split( line )
         if len( name_around ) == 3:
            self.name = name or name_around[1]
            name_around = name_around[2:]
         elif len( name_around ) != 1:
            raise ValueError( 'Too many "s in line: ' + line )
         
         seq = re.split( r" *[;=] *", name_around[0] )
         try:
            _, t, *_ = dropwhile( lambda x: x != "dur", seq )
         except ValueError:
            pass
         else:
            m,s = ":".split( t )
            self.dur = dur or timedelta( minutes=int(m), seconds=int(s) )

   def overlay( self, other ):
      if self.name != other.name:
         raise ValueError( "Can only overlay Entry's with same name, got: "\
                           + other.name + " for " + self.name )
      self.children += other.children
      for attr in self.copy_attrs:
         oa = getattr( other, attr )
         if oa:
            setattr( self, attr, oa )
      return self

def create( revue ):
   known_entries = [ Entry( name="", dur=timedelta(0) ) ]
   for act in revue.acts:
      known_entries += [ Entry( name = act.name ) ] \
         + [ Entry( name = mat.title, dur = mat.dur ) for mat in act.materials ]
   waiting = []
   
   def switch_to( line ):
      entry = Entry( line )
      try:
         mother = next( kn for kn in known_entries if kn.name == entry.name )
      except StopIteration:
         waiting += [ entry ]
      else:
         waiting.children += waiting[1:]
         waiting = [ mother.overlay( entry ) ]
      return waiting

   with open( conf["Files"]["timesheet-info"], "r" ) as f:
      for l in f:
         l.strip()
         if l.startswith( "#" ): # comment
            continue
         if l.startswith( '"' ): # named revue object
            waiting = switch_to( l )
         if l.startswith( "-" ): # extra steps
            waiting += [ Entry( l ) ]
