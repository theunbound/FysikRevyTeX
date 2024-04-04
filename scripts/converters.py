# -*- coding: utf-8 -*-
import os
import shutil
import subprocess
import tempfile
import uuid
from multiprocessing import Pool, cpu_count
from multiprocessing.managers import BaseManager
from time import time, sleep
from rich.live import Live
import asyncio

from config import configuration as conf

import output

# fordi https://learn.microsoft.com/en-us/windows/security/threat-protection/security-policy-settings/create-symbolic-links
# tak, windows.
try:
    import _winapi
    def portable_dir_link( source, target ):
        _winapi.CreateJunction( source, target )
except ImportError:
    def portable_dir_link( source, target ):
        os.symlink( source, target )
        
class ConversionError( Exception ):
    pass

class MyManager(BaseManager):
    pass

MyManager.register( "GridManager", output.GridManager )

class GMD():
    def new_row_number(*args):
        pass
    def state_for_number(*args):
        pass
    def activity_ping_number(*args):
        pass

class Converter:
    def __init__(self):
        self.conf = conf

    def textopdf(self, *args, **kwargs):
        """
        Dummy wrapper method to make multiprocessing work on a 
        decorated function.
        """
        print( args, kwargs )
        self._textopdf(*args, **kwargs)

    def _textopdf(self, tex, pdfname="", outputdir="", repetitions=2, encoding='utf-8', grid_manager=GMD() ):
    #def textopdf(self, tex, pdfname="", outputdir="", repetitions=2, encoding='utf-8'):
        "Generates a PDF from either a TeX file or TeX object."

        if outputdir == "":
            outputdir = self.conf["Paths"]["pdf"]

        src_dir = os.getcwd()
        src_modtime = time()    # Gå ud fra helt ny

        if type(tex) == str and tex.strip()[-3:] == 'tex':
            # Object is a file path string.
            input_is_tex_file = True
            src_modtime = os.stat( tex ).st_mtime
        else:
            input_is_tex_file = False
            temp = tempfile.mkdtemp()

        if input_is_tex_file:
            # Object is a file path string.
            # The TeXing should be done in the original directory to avoid
            # problems with e.g. included figures not being copied to the
            # temporary directory.
            path, texfile = os.path.split(tex.strip())
            pdffile = "{}.pdf".format(texfile[:-4])
            dst_dir = os.path.join(src_dir, outputdir,
                                   os.path.relpath( path, src_dir ))

        elif type(tex) == str and tex.strip()[-3:] != 'tex':
            # Object is a string of TeX code.
            tempname = uuid.uuid4() # Generate unique name
            texfile = "{}.tex".format(tempname)
            pdffile = "{}.pdf".format(tempname)
            dst_dir = os.path.join(src_dir, outputdir)

            with open(os.path.join(temp, texfile), 'w', encoding=encoding) as f:
                f.write(tex)

        elif type(tex).__name__ == "TeX":
            # Object is a TeX object.
            if tex.fname:
                fname = tex.fname[:-4]
            else:
                fname = uuid.uuid4() # Generate unique name
            texfile = "{}.tex".format(fname)
            pdffile = "{}.pdf".format(fname)
            src_modtime = tex.info[ "modification_time" ]
            tex.write(os.path.join(temp,texfile), encoding=encoding)
            dst_dir = os.path.join(src_dir, outputdir)

        elif type(tex).__name__ == "Material":
            # Object is a Material object.
            # The TeXing should be done in the original directory to avoid
            # problems with e.g. included figures not being copied to the
            # temporary directory.
            path, texfile = os.path.split(tex.path.strip())
            pdffile = "{}.pdf".format(texfile[:-4])
            dst_dir = os.path.join(src_dir, outputdir,
                                   os.path.relpath( path, src_dir ))
            input_is_tex_file = True
            src_modtime = tex.modification_time

        else:
            raise TypeError("Input should be either TeX code, a string of a "
                            ".tex file, a TeX object or a Material object.")
        if pdfname == "":
            pdfname = pdffile

        try:
            if ( os.stat( os.path.join(dst_dir, pdfname or pdffile ) ).st_mtime
                 > src_modtime
                 and not self.conf.getboolean(
                     "TeXing", "force TeXing of all files"
                 )):
                on = grid_manager.new_row_number(
                    output.States.skipped, pdfname
                )
                return          # hop fra, når output er nyere end input
        except FileNotFoundError:
            # outputfilen findes ikke. Vi laver den
            pass                

        if input_is_tex_file:
            os.chdir(path)
        else:
            os.chdir(temp)
            if os.path.exists( os.path.join( src_dir, "revy.sty" ) ):
                shutil.copy(os.path.join(src_dir,"revy.sty"), "revy.sty")
            if os.path.exists( os.path.join( src_dir, "ucph-revy.cls" ) ):
                shutil.copy(os.path.join(src_dir,"ucph-revy.cls"), "ucph-revy.cls")
                print( os.listdir(".") )
            portable_dir_link( src_dir, "src_dir" )

        on = grid_manager.new_row_number( output.States.texing, pdfname )
        rc = None
        for i in range(repetitions):
            tex_proc = subprocess.Popen(
                ["pdflatex", "-interaction=nonstopmode", texfile],
                stdout = subprocess.PIPE,
                stderr = subprocess.STDOUT,
                text = True)
            while True:
                o,e = "",""
                try:
                    o,e = tex_proc.communicate( timeout = 1 )
                except subprocess.TimeoutExpired:
                    pass
                finally:
                    for n in o:
                        if n == "\n":
                            grid_manager.activity_ping_number( on )
                rc = tex_proc.returncode
                if rc != None:
                    break
            # if self.conf.getboolean("TeXing","verbose output"):
            #     rc = subprocess.call(["pdflatex", "-interaction=nonstopmode", texfile])
            # else:
            #     rc = subprocess.call(["pdflatex", "-interaction=batchmode", texfile], 
            #                          stdout=subprocess.DEVNULL)


        # Check whether the pdf was generated:
        # TODO: This needs to be done better.
        # if not os.path.isfile(pdffile):
        #     rerun = input("Oh snap! Something went wrong when creating the PDF.\n"
        #                   "Do you want to run pdflatex again, this time with output? (y/[n])")
        #     if rerun == 'y':
        #         rc = subprocess.call(["pdflatex", texfile]) 


        # print("{:<42}".format("\033[0;37;1m{}:\033[0m".format(pdfname or pdffile)), end="")
        if rc == 0:
            # print("\033[0;32m Success!\033[0m")
            grid_manager.state_for_number( on, output.States.success )
        elif os.path.exists( pdffile ):
            # print("\033[0;33m Had Errors!\033[0m" )
            grid_manager.state_for_number( on, output.States.errors )
        else:
            # print("\033[0;31m Failed!\033[0m")
            grid_manager.state_for_number( on, output.States.failed )
            raise ConversionError

        if pdfname != pdffile:
            os.rename(pdffile, pdfname)

        try:
            if not os.path.isdir( dst_dir ):
                os.makedirs( dst_dir )
            shutil.move(pdfname, dst_dir)
        except shutil.Error:
            os.remove(os.path.join(dst_dir, pdfname))
            shutil.move(pdfname, dst_dir)

        os.chdir(src_dir)

        if input_is_tex_file:
            os.remove("{}.aux".format(os.path.join(path,texfile[:-4])))
            os.remove("{}.log".format(os.path.join(path,texfile[:-4])))
        else:
            shutil.rmtree(temp)


    def parallel_textopdf(self, file_list,
                          outputdir="",
                          repetitions=2,
                          encoding='utf-8'):

        new_file_list = []
        for el in file_list:
            if type(el) == list and type(el[1]) == str:
                file_path = el[0]
                pdfname = el[1]
            else:
                file_path = el
                pdfname = ""

            new_file_list.append((file_path, pdfname, outputdir, repetitions, encoding))

        # with Pool(processes = cpu_count()), Live( refresh_per_second=10 ) \
        #      as pool,live:

        with MyManager() as mgr,\
             Pool( processes = cpu_count()) as pool:
            gm = mgr.GridManager( refresh_per_second = 10 )
            tn = gm.new_row_number( output.States.skipped, "Start test" )
            self.textopdf( *new_file_list[0], gm )
            # result = pool.starmap(self.textopdf, new_file_list + (live,))


