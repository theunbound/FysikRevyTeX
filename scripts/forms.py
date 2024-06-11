from configparser import NoSectionError, NoOptionError
from functools import cache
from urllib import request
from urllib.error import URLError
from datetime import datetime, date, timedelta
import re, urllib

from apiclient import discovery
from httplib2 import Http
from oauth2client import client, file, tools
from oauth2client.clientsecrets import InvalidClientSecretsError
from ics import Calendar, Event
from ics.grammar.parse import ParseError
from pytz import timezone

from classy_revy import Act, Material
from base_classes import Role
from config import configuration
conf = configuration.conf

SCOPES = "https://www.googleapis.com/auth/forms.body"
DISCOVERY_DOC = "https://forms.googleapis.com/$discovery/rest?version=v1"
CREDENTIALS_DEFAULT_FILE_NAME = "credentials.json"
DEFAULT_TEMPLATE_FORM_ID = "1HmrpySe-A8ZwzpfNnOkLiGjHGizxZ6KAnJrEh-Rk2LM"

store = file.Storage( conf.get( "Forms", "token json",
                                fallback = "token.json" ) )

form_service = None
template_form = None

try:
  template_form = form_service\
    .forms()\
    .get( formId = conf.get( "Forms", "template forms id" ) )\
    .execute()
except (NoSectionError, NoOptionError): # but what if wrong id ???????
  if type( e ) == NoSectionError:
    conf.add_section( "Forms" )
  template_form_id = input("""
Den nye google-form skal baseres på en eksisterende form, hvor der
er sat mærker ind der, hvor vores autogenererede indhold skal sættes
ind. Se
https://docs.google.com/forms/d/1HmrpySe-A8ZwzpfNnOkLiGjHGizxZ6KAnJrEh-Rk2LM/edit
for et eksempel. Forms-skabelonen bliver ikke ændret. Vi laver en kopi
med det autogenererede indhold i stedet.

forms-id: [{}]: """.format( DEFAULT_TEMPLATE_FORM_ID )
  ) or DEFAULT_TEMPLATE_FORM_ID
  

new_form = {}
new_form["info"] = {}
new_form["info"]["title"] = \
  template_form["info"]["title"] + " genereret af FysikRevyTeX"
new_form["info"]["documentTitle"] = \
  template_form["info"]["documentTitle"] + " genereret af FysikRevyTeX"

def walk_item( item ):
  if type( item ) == dict:
    result = set()
    for key in item:
      result |= walk_item( item[ key ] )
    return result
  if type( item ) == list:
    result = set()
    for internal in item:
      result |= walk_item( internal )
    return result
  try:
    if "<+" in item:
      return { placeholder for placeholder in \
               re.findall( r"<\+([^+]*)\+>", item )
              }
  except TypeError:
    pass
  return set()

def copy_tree( tree ):
  if type( tree ) == list:
    return [ copy_tree( branch ) for branch in tree ]
  if type( tree ) == dict:
    return { key: copy_tree( value )
             for (key,value) in tree if "Id" not in key }
  return tree

@cache
def planned_times():
  @cache
  def explain():
    print("""
Forms-skabelonen spørger efter planlagte tidspunkter med
'<+MØDETIDSPUNKTER+>'. Vi kigger efter tidspunkter i en
iCalendar-fil.

""")
  
  while True:
    try:
      calendar_location = conf.get( "Forms", "calendar file" )
      try:
        with urllib.request.urlopen( calendar_location ) as req:
          revykalender = Calendar( req.read() )
          break
      except (ValueError, URLError):
        with open( calendar_location, "r", encoding="utf-8" ) as f:
          revykalender = Calendar( f.read() )
          break
    except ( NoSectionError, NoOptionError,
             FileNotFoundError, OSError, ParseError ) as e:
      explain()
      if type( e ) in [ NoSectionError, NoOptionError ]:
        print("Du bliver nødt til at fortælle, hvor sådan en kan findes.")
      else:
        print("Filen {}".format( conf.get( "Forms", "calendar file" ) ) )
      if type( e ) in [ FileNotFoundError, OSError ]:
        print("kan ikke åbnes. Er stien korrekt?\n")
      if type( e ) == ParseError:
        print(
          "lader ikke til at være en gyldig iCalendar-fil. Prøv noget andet?\n"
        )

      new_location = input("""
Det her punkt kan skippes, hvis du trykker <Enter> uden at skrive noget.
     
iCalendar-fil (sti eller url): [<Spring over>]: """)

      if not new_location:
        return [ "<+MØDETIDSPUNKT+>" ]
      if type( e ) == NoSectionError:
        conf.add_section( "Forms" )
      conf.set( "Forms", "calendar file", new_location )

  while True:
    try:
      date_range = [ datetime.fromisoformat( ds )
                     for ds in [ conf.get( "Forms", "date range start" ),
                                 conf.get( "Forms", "date range end" ) ]
                    ]
      break
    except ( NoSectionError, NoOptionError, ValueError ) as e:
      cal_limits = None
      for event in revykalender.timeline:
        cal_limits = cal_limits or [ event.begin, None ]
        cal_limits[1] = event.end

      if type( e ) == ValueError:
        print("\nKunne ikke afkode dato:")
        print( e.args[0] )
      else:
        print("\nFilen {}\nindeholder begivenheder i datointervallet {} – {}."\
              .format( conf.get( "Forms", "calendar file" ),
                       *[ time.date().isoformat() for time in cal_limits ] ) )

        print("""\
Hvis du kun vil have begivenheder i et kortere interval med i den nye
Form, så kan du skrive et nyt interval nu. Fx er de næste 90 dage:
{} {}""".format( date.today().isoformat(),
                 (date.today() + timedelta( days = 90 )).isoformat()
                )
              )

      answer = input("\nDatointerval: [{} {}]: ".format(
        *[ time.date().isoformat() for time in cal_limits ]
      )).strip()

      if type( e ) == NoSectionError:
        conf.add_section( "Forms" )
      conf.set( "Forms", "date range start",
                answer[0:10] if answer else cal_limits[0].isoformat() )
      conf.set( "Forms", "date range end",
                answer[-10:] if answer else cal_limits[1].isoformat() )

  try:
    date.fromisoformat( conf.get( "Forms", "date range end" ) )
  except ValueError:
    pass
  else:
    # hvis det er en dato (ikke et tidspunkt) så er det tom. den dato
    date_range[1] = date_range[1] + timedelta( days = 1 )
    
  date_range = [ ( dato.replace( tzinfo = timezone( "Europe/Copenhagen" ) )
                   if not dato.tzinfo else dato )\
                 .astimezone( timezone( "Europe/Copenhagen" ) )
                 for dato in date_range
                ]
  ugedage = ["Mandag","Tirsdag","Onsdag","Torsdag","Fredag","Lørdag","Søndag"]

  while True:
    try:
      times = []
      for revyevent in revykalender.timeline.included( *date_range ):
        if not revyevent.all_day or \
           not conf.getboolean( "Forms", "filter all day events" ):
          
          begin, end = ( t.astimezone( timezone( "Europe/Copenhagen" ) ) 
                         for t in ( revyevent.begin, revyevent.end ) )
          times += [
            "{}: {} d. {}/{}".format(
              revyevent.name,
              ugedage[ revyevent.begin.weekday() ],
              begin.day,
              begin.month
            ) + (
              (" – {}/{}".format(
                end.day,
                end.month
              ) if end - begin > timedelta( days=1 ) else ""
               ) if revyevent.all_day
              else ", {}:{:0>2} – {}:{:0>2}".format(
                  begin.hour,
                  begin.minute,
                  end.hour,
                  end.minute
              )
            )
          ]
      return times
    except (NoSectionError, NoOptionError, ValueError):
      conf.set(
        "Forms", "filter all day events",
        input("\nFiltrér heldagsbegivenheder fra? yes/[no]: ").strip() or "no"
      )

def copy_tree_replace_placeholder_or_listfunc(
    tree, placeholder, replacement, listfunc
):
  if type( tree ) == list:
    return ( False, listfunc( tree ) )
  if type( tree ) == dict:
    new_dict = {}
    it_was_found = False
    for key in tree:
      if "Id" in key:
        continue

      found_it, branch_copy = copy_tree_replace_placeholder_or_listfunc(
        tree[ key ], placeholder, replacement, listfunc
      )

      new_dict[ key ] = branch_copy
      it_was_found = it_was_found or found_it

    return ( it_was_found, new_dict )

  try:
    if "<+" + placeholder + "+>" in tree:
      return ( True, tree.replace( "<+" + placeholder + "+>", replacement ) )
  except TypeError as e:
    if "is not iterable" not in e.args[0]:
      raise e

  return ( False, tree )

placeholder_info = (
  { "type": Act,
    "placeholder": "AKTTITEL",
    "namer": lambda act: act.name,
    "level_down": lambda act: act.materials
   },
  { "type": Material,
    "placeholder": "MATERIALETITEL",
    "namer": lambda mat: mat.title,
    "level_down": lambda mat: mat.roles
   },
  { "type": Role,
    "placeholder": "ROLLE",
    "namer": lambda role: \
      role.abbreviation + ( " ({})".format( role.role ) if role.role else "" ),
    "level_down": lambda arg: []
   },
)

planned_times_info = (
  { "type": str,
    "placeholder": "MØDETIDSPUNKT",
    "namer": lambda name: name,
    "level_down": lambda arg: []
   },
)

def revy( items, replacements, placeholder_info ): # think revy.acts
  try:
    revy_depth = [ info["type"] for info in placeholder_info ]\
      .index( type( replacements[0] ) )
  except IndexError:
    return items
  
  output = []
  pen = []
  maybe_pen = []

  def replace_in_items( r_items ):
    r_output = []
    did_replacement = False
    output_buffer = []
    for replacement in replacements:

      def sublist_discriminate( sub_list ):
        sub_placeholders = walk_item( sub_list )
        if placeholder_info[ revy_depth ]["placeholder"] \
           in sub_placeholders:
          return revy( sub_list, replacements, placeholder_info )
        try:
          if placeholder_info[ revy_depth + 1 ]["placeholder"] \
             in sub_placeholders:
            return revy(
              sub_list,
              placeholder_info[ revy_depth ]["level_down"]( replacement ),
              placeholder_info
            )
        except IndexError:
          pass
        return sub_list

      for current_item in r_items:
        repd, new_item = copy_tree_replace_placeholder_or_listfunc(
          current_item,
          placeholder_info[ revy_depth ]["placeholder"],
          placeholder_info[ revy_depth ]["namer"]( replacement ),
          sublist_discriminate
        )

        did_replacement = repd or did_replacement
        output_buffer += [ new_item ]

      if not did_replacement:
        break

      r_output += revy(
        output_buffer,
        placeholder_info[ revy_depth ]["level_down"]( replacement ),
        placeholder_info
      )
      output_buffer = []

    else:                       # no break
      return r_output + output_buffer

    return revy(
      output_buffer,
      [ sub_rep for rep in replacements
        for sub_rep in placeholder_info[ revy_depth ]["level_down"]( rep )
       ],
      placeholder_info
    )
  
  for item in items:
    discovery = walk_item( item )
    if placeholder_info[ revy_depth ]["placeholder"] in discovery:
      output += replace_in_items( pen + maybe_pen )
      pen = [ item ]
      maybe_pen = []
    elif any( info["placeholder"] in discovery
              for info in placeholder_info[ revy_depth + 1: ] ):
      pen += maybe_pen + [ item ]
      maybe_pen = []
    else:
      maybe_pen += [ item ]

  output += replace_in_items( pen ) + maybe_pen
  return output

def google_form_setup():
  while True:
    try:
      creds = tools.run_flow(
        client.flow_from_clientsecrets(
          conf.get( "Forms", "credentials json" ), SCOPES
        ),
        store
      )
      break
    except ( InvalidClientSecretsError, NoSectionError, NoOptionError ) as e:
      if type( e ) == NoSectionError:
        conf.add_section( "Forms" )
      if type( e ) in [ NoSectionError, NoOptionError ]:
        print("Programmet skal bruge en fil med credentials til Google.")
      if type( e ) == InvalidClientSectionError:
        print("Det ser ikke ud til, at '{}'".format(
          conf.get( "Forms", "credentials json" )
        ))
        print("er filen med credentials til Google.")

      conf.set( "Forms", "credentials json", (
        input( """\
Hvis du ikke har sådan en fil endnu, så er der instruktioner her:
https://developers.google.com/forms/api/quickstart/python#set_up_your_environment

Credentials-fil [{}]: """.format( CREDENTIALS_DEFAULT_FILE_NAME )
              )
        or CREDENTIALS_DEFAULT_FILE_NAME
      ))

  form_service = discovery.build(
      "forms",
      "v1",
      http=creds.authorize(Http()),
      discoveryServiceUrl=DISCOVERY_DOC,
      static_discovery=False,
  )


def new_form_from_template( revue ):
  
  result = form_service.forms().create( body = new_form ).execute()
  form_service.forms().batchUpdate(
    formId = result["formId"],
    body = {
      "requests": [
        {
          "createItem": {
            "item": item,
            "location": {"index": i}
          }
        }
        for i,item in enumerate(
            revy(
              revy( template_form["items"], revue.acts, placeholder_info ),
              planned_times(),
              planned_times_info
            )
        )
      ]
    }
  ).execute()

  if conf.has_section( "Forms" ):
    print( "\n[Forms]" )
    for item in conf.items("Forms"):
      print( "{} = {}".format( *item ) )

google_form_setup()
