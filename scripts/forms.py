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

from config import configuration
conf = configuration.conf

SCOPES = "https://www.googleapis.com/auth/forms.body"
DISCOVERY_DOC = "https://forms.googleapis.com/$discovery/rest?version=v1"

store = file.Storage( conf.get( "Forms", "token json",
                                fallback = "token.json" ) )
cred_file = conf.get( "Forms", "credentials json",
                      fallback = "credentials.json" )

while True:
  try:
    creds = tools.run_flow(
      client.flow_from_clientsecrets( cred_file, SCOPES ),
      store
    )
    break
  except InvalidClientSecretsError as e:
    if e.args[0] == "Error opening file":
      cred_file = input( """
Det ser ikke ud til, at '{}' er filen med credentials til Google. Hvis
du ikke har sådan en fil endnu, så er der instruktioner her:
https://developers.google.com/forms/api/quickstart/python#set_up_your_environment

Credentials-fil [{}]: """.format( cred_file, cred_file ) ) or cred_file
    else:
      raise e

form_service = discovery.build(
    "forms",
    "v1",
    http=creds.authorize(Http()),
    discoveryServiceUrl=DISCOVERY_DOC,
    static_discovery=False,
)

try:
  template_form_id = conf.get( "Forms", "template forms id" )
except (NoSectionError, NoOptionError):
  default_template_form_id = "1HmrpySe-A8ZwzpfNnOkLiGjHGizxZ6KAnJrEh-Rk2LM"
  template_form_id = input("""
Den nye google-form skal baseres på en eksisterende form, hvor der
er sat mærker ind der, hvor vores autogenererede indhold skal sættes
ind. Se
https://docs.google.com/forms/d/1HmrpySe-A8ZwzpfNnOkLiGjHGizxZ6KAnJrEh-Rk2LM/edit
for et eksempel. Forms-skabelonen bliver ikke ændret. Vi laver en kopi
med det autogenererede indhold i stedet.

forms-id: [{}]: """.format( default_template_form_id )
  ) or default_template_form_id
  
template_form = form_service.forms().get( formId = template_form_id ).execute()
new_form = {}

new_form["info"] = {}
new_form["info"]["title"] = \
  template_form["info"]["title"] + " fra FysikRevyTeX"
new_form["info"]["documentTitle"] = \
  template_form["info"]["documentTitle"] + " fra FysikRevyTeX"

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

class FoundIt( Exception ):
  pass

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
  
def mødetidspunkt( item ):
  if type( item ) == dict:
    did_replacement, new_item = copy_tree_replace_placeholder_or_listfunc(
      item, "MØDETIDSPUNKT", planned_times()[0], mødetidspunkt
    )

    if did_replacement:
      return [ new_item ] + [ copy_tree_replace_placeholder_or_listfunc(
        item, "MØDETIDSPUNKT", planned_time, mødetidspunkt
      )[1] for planned_time in planned_times()[1:] ]
    else:
      return [ new_item ]
    
  if type( item ) == list:
    return [ new_el for el in item for new_el in mødetidspunkt( el ) ]

  return [ copy_tree_replace_placeholder_or_listfunc(
    item, "MØDETIDSPUNKT", planned_times()[0], mødetidspunkt,
  )[1] ]

def act( item, akt ):
  if type( item ) == list:
    return [ new_el for el in item for new_el in act( el, akt ) ]
  if type( item ) == dict:
    did_replacement, new_item = copy_tree_replace_placeholder_or_listfunc(
      item, "AKTTITEL", akt[0].name, lambda oi: act( oi, akt ) # closure?
    )
    return [ mats( new_item, akt[0].materials ) ] \
      + ( [ mats(
        copy_tree_replace_placeholder_or_listfunc(
          item, "AKTTITEL", akt_i.name, lambda oi: act( oi, akt_i )
        )) for akt_i in akt[1:]
           ] if did_replacement else []
         )
  return [ copy_tree_replace_placeholder_or_listfunc(
    item, "AKTTITEL", akt[0].name, lambda oi: act( oi, akt )
  )[1] ]

def magic( item, placeholder, replacements,
           replc_stringifyer = lambda *args: args[0],
           sub_magic = lambda *args: args[0]
          ):
  def repeat_magic( sub_item ):
    return magic( sub_item, placeholder, replacements,
                  replc_stringifyer, sub_magic
                 )
  
  if type( item ) == list:
    return [ new_el for el in item for new_el in repeat_magic( el ) ]
  if type( item ) == dict:
    did_replacement, new_item = copy_tree_replace_placeholder_or_listfunc(
      item, placeholder, replc_stringifyer( replacements[0] ), repeat_magic
    )

    return [ sub_magic( new_item, replacements[0] ) ] \
      + (
        [
          sub_magic(
            copy_tree_replace_placeholder_or_listfunc(
              item, placeholder, replc_stringifyer( replacement ), repeat_magic
            )[1],
            replacement
          ) for replacement in replacements[1:]
        ] if did_replacement else []
      )

  return [ copy_tree_replace_placeholder_or_listfunc(
    item, placeholder, replc_stringifyer( replacements[0] ), repeat_magic
  )[1] ]



def revy( items, current_ladder ):
  output = []
  pen = []
  maybe_pen = []
  for item in items:
    if current_ladder[0] in walk_item( item ):
      output += revy( pen + maybe_pen, current_ladder[1:] )
      pen = [ item ]
      maybe_pen = []
    elif any( found in current_ladder for found in walk_item( item ) ):
      pen += maybe_pen + [ item ]
      maybe_pen = []
    else:
      maybe_pen += [ item ]

  if current_ladder:
    output += revy( pen, current_ladder[1:] )
  return output

for item in template_form["items"]:
  for key in item:
    if "Id" in key:
      continue
    for placeholder in walk_item( item ):
      # active_items[ placeholder ].add( item )
      pass
      # well, that doesn't work...

if conf.has_section( "Forms" ):
  print( "\n[Forms]" )
  for item in conf.items("Forms"):
    print( "{} = {}".format( *item ) )

# new_form["items"] = []
# for item in template_form["items"]:

#   new_item = {}
  
#   if item in all_active_items:
#     if item in active_items["MÆDETIDSPUNKT"]:
      
#   else:
#     for entry in item:
#       if "Id" in entry:
#         continue
#       new_item[ entry ] = copy_tree( item[ entry ] )
      
#   new_form["items"] += [ new_item ]

# # Request body for creating a form
# NEW_FORM = {
#     "info": {
#         "title": "Quickstart form",
#     }
# }

# # Request body to add a multiple-choice question
# NEW_QUESTION = {
#     "requests": [
#         {
#             "createItem": {
#                 "item": {
#                     "title": (
#                         "In what year did the United States land a mission on"
#                         " the moon?"
#                     ),
#                     "questionItem": {
#                         "question": {
#                             "required": True,
#                             "choiceQuestion": {
#                                 "type": "RADIO",
#                                 "options": [
#                                     {"value": "1965"},
#                                     {"value": "1967"},
#                                     {"value": "1969"},
#                                     {"value": "1971"},
#                                 ],
#                                 "shuffle": True,
#                             },
#                         }
#                     },
#                 },
#                 "location": {"index": 0},
#             }
#         }
#     ]
# }

# # Creates the initial form
# result = form_service.forms().create(body=NEW_FORM).execute()

# # Adds the question to the form
# question_setting = (
#     form_service.forms()
#     .batchUpdate(formId=result["formId"], body=NEW_QUESTION)
#     .execute()
# )

# # Prints the result to show the question has been added
# get_result = form_service.forms().get(formId=result["formId"]).execute()
# print(get_result)
