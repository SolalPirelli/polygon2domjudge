#!/usr/bin/env python
import argparse,binascii,hashlib,os,math,tempfile,time,shutil,subprocess,sys
from distutils.dir_util import copy_tree
from shutil import copyfile,make_archive,rmtree
import xml.etree.ElementTree

def ensure_dir(s):
	if not os.path.exists(s):
		os.makedirs(s)

def ensure_no_dir(s):
	if os.path.exists(s):
		rmtree(s)


PACKAGE_DIR='poly/'
TEMP_DIR = tempfile.gettempdir() + '/polygon2domjudge'
OUTPUT_PATH='.'
OUTPUT_DIR=OUTPUT_PATH+'/domjudge/'
EXTENSION_FOR_OUTPUT = '.a'
EXTENSION_FOR_DESC = '.desc'
sample_tests = ['01']
PROBCODE = "PROB1"
PROBCOLOR = "#000000"
nodelete = False

#PARSING COMMAND LINE ARGUMENTS
parser = argparse.ArgumentParser(description='Process Polygon Package to Domjudge Package.')
parser.add_argument('package', type=str, help='path of the polygon package')
parser.add_argument('--code',  type=str, help='problem code for domjudge')
parser.add_argument('--sample',type=str, help='Specify the filename for sample test. Defaults to \'01\'')
parser.add_argument('--num-samples', type=str, help='Specify the number of sample test cases. Defaults to \'1\'')
parser.add_argument('--color', type=str, help='problem color for domjudge (in RRGGBB format)')
parser.add_argument('-o','--output', type=str, help='Output Package directory')
parser.add_argument('--no-delete', action='store_true', help='Don\'t delete the output directory')
parser.add_argument('--add-html', action='store_true', help='Add Problem statement in HTML form')
parser.add_argument('--pdf-from-latex', action='store_true', help='Create a PDF from the LaTeX file (work around polygon bad pdf generation)')
parser.add_argument('--ext', type=str, help='Set extension for the OUTPUT files in testset')
parser.add_argument('--custom-checker', action='store_true', help='Treat checker as non-standard: create domjudge checker from it')
args = parser.parse_args()
if args.code:
	PROBCODE = args.code

if args.color:
	PROBCOLOR = '#'+args.color

if args.sample:
	sample_tests = [args.sample]

if args.num_samples:
    assert len(sample_tests) == 1
    first = int(sample_tests[0])
    num_samples = int(args.num_samples)
    assert(num_samples < 100)
    sample_tests = ['{0:02d}'.format(i) for i in range(first, first + num_samples)]

if args.output:
	OUTPUT_PATH = args.output
	OUTPUT_DIR=OUTPUT_PATH+'/domjudge/'

if args.ext:
	EXTENSION_FOR_OUTPUT = args.ext

if args.no_delete:
	nodelete = True


package_name = os.path.splitext(os.path.basename(args.package))[0]

#Extracting the packages
def extract(pkg, output):
	import zipfile
	if not os.path.isfile(pkg):
		print "[ERROR] " + pkg + " NOT FOUND"
		exit(1)
	zip_ref = zipfile.ZipFile(pkg, 'r')
	ensure_no_dir(output)
	zip_ref.extractall(output)
	zip_ref.close()

extract(args.package, PACKAGE_DIR)

#Create the OUTPUT DIR
ensure_no_dir(OUTPUT_DIR)
ensure_dir(OUTPUT_DIR)

if args.add_html:
	copyfile(PACKAGE_DIR+'/statements/.html/english/problem.html',OUTPUT_DIR+'problem.html')
	copyfile(PACKAGE_DIR+'/statements/.html/english/problem-statement.css',OUTPUT_DIR+'problem-statement.css')

#Create Sub DIRS for tests
ensure_dir(OUTPUT_DIR+'/data')
ensure_dir(OUTPUT_DIR+'/data/sample')
ensure_dir(OUTPUT_DIR+'/data/secret')

#Create Sub DIRS for jury submissions
ensure_dir(OUTPUT_DIR + '/submissions')

#Parse XML for Problem Data
root = xml.etree.ElementTree.parse(PACKAGE_DIR+'problem.xml').getroot()
problem_name = root.find('names').find('name').attrib['value']
timelimit = int(math.ceil(float(root.find('judging').find('testset').find('time-limit').text)/1000.0))
print('TIME LIMIT IS ' + str(timelimit))

checker_name = None
if args.custom_checker:
	checker = root.find('assets').find('checker')
	checker_source = checker.find('source')
	if checker_source.attrib['type'].startswith('cpp.g++'):
		ensure_dir(TEMP_DIR)
		TESTLIB_PATH = TEMP_DIR + '/testlib.h'

		# Download testlib, unless it already exists and was downloaded < 1d ago
		if os.path.exists(TESTLIB_PATH) and (time.time() - os.path.getmtime(TESTLIB_PATH)) > 60 * 60 * 24:
			os.remove(TESTLIB_PATH)
		if not os.path.exists(TESTLIB_PATH):
			print('Downloading testlib...')
			TESTLIB_ONLINE_PATH = 'https://raw.githubusercontent.com/MikeMirzayanov/testlib/master/testlib.h'
			import urllib
			urllib.urlretrieve(TESTLIB_ONLINE_PATH, TESTLIB_PATH)

		SCRIPT_DIR = os.path.dirname(os.path.realpath(sys.argv[0]))
		CHECKER_DIR = TEMP_DIR + '/checker'
		ensure_dir(CHECKER_DIR)
		copyfile(TESTLIB_PATH, CHECKER_DIR + '/testlib.h')
		copyfile(SCRIPT_DIR + '/checker/build', CHECKER_DIR + '/build')
		os.chmod(CHECKER_DIR + '/build', 0777)
		copyfile(SCRIPT_DIR + '/checker/run', CHECKER_DIR + '/run')
		os.chmod(CHECKER_DIR + '/run', 0777)
		copyfile(PACKAGE_DIR + '/' + checker_source.attrib['path'], CHECKER_DIR + '/checker.cpp')

		make_archive(TEMP_DIR + '/checker', 'zip', CHECKER_DIR)

		with open(TEMP_DIR + '/checker.zip', 'rb') as archive:
			archive_bin = archive.read()
		archive_hex = binascii.hexlify(archive_bin)

		hasher = hashlib.md5()
		hasher.update(archive_bin)
		archive_md5 = hasher.hexdigest()

		checker_name = package_name + '-checker'

		# REPLACE INTO will delete then insert, but that's ok since executables aren't referred to via foreign keys
		sql_statement = "REPLACE INTO domjudge.executable(execid, md5sum, zipfile, type) VALUES ('" + checker_name + "', '" + archive_md5 + "', 0x" + archive_hex + ", 'compare');"
		with open(OUTPUT_PATH + '/' + package_name + '-domjudge.sql', 'w') as sql:
			sql.write(sql_statement)
		print('WARNING: Package ' + package_name + ' contains a custom checker. Make sure you run the generated sql BEFORE importing the problem.')

		rmtree(CHECKER_DIR)
		os.remove(TEMP_DIR + '/checker.zip')
	else:
		print('ERROR: Package ' + package_name + ' contains a custom checker not written in C++. This is not supported by the script.')

desc = open(OUTPUT_DIR+'domjudge-problem.ini','w+')
desc.write("probid='"+PROBCODE+"'\n")
desc.write("name='"+problem_name.replace("'","`")+"'\n")
desc.write("timelimit='"+str(timelimit)+"'\n")
desc.write("color='"+PROBCOLOR+"'\n")
if checker_name is not None:
	desc.write("special_compare='" + checker_name + "'\n")
desc.close()

tests = filter(lambda x:not x.endswith(EXTENSION_FOR_OUTPUT),os.listdir(PACKAGE_DIR+'/tests'))
for test in tests:
	if test in sample_tests:
		copyfile(PACKAGE_DIR+'/tests/'+test,OUTPUT_DIR+'/data/sample/'+test+'.in')
		copyfile(PACKAGE_DIR+'/tests/'+test+EXTENSION_FOR_OUTPUT,OUTPUT_DIR+'/data/sample/'+test+'.ans')
	else:
		copyfile(PACKAGE_DIR+'/tests/'+test,OUTPUT_DIR+'/data/secret/'+test+'.in')
		copyfile(PACKAGE_DIR+'/tests/'+test+EXTENSION_FOR_OUTPUT,OUTPUT_DIR+'/data/secret/'+test+'.ans')

jury_solutions = filter(lambda x : not x.endswith(EXTENSION_FOR_DESC), os.listdir(PACKAGE_DIR + '/solutions'))
for solution in jury_solutions:
    copyfile(PACKAGE_DIR + '/solutions/' + solution, OUTPUT_DIR + '/submissions/' + solution)


if args.pdf_from_latex:
	ensure_dir(TEMP_DIR)

	OLYMP_PATH = TEMP_DIR + '/olymp.sty'
	# Download olymp.sty, unless it already exists and was downloaded < 1d ago
	if os.path.exists(OLYMP_PATH) and (time.time() - os.path.getmtime(OLYMP_PATH)) > 60 * 60 * 24:
		os.remove(OLYMP_PATH)
	if not os.path.exists(OLYMP_PATH):
		print('Downloading olymp...')
		OLYMP_ONLINE_PATH = 'https://raw.githubusercontent.com/GassaFM/olymp.sty/master/statements/olymp.sty'
		import urllib
		urllib.urlretrieve(OLYMP_ONLINE_PATH, OLYMP_PATH)

	SCRIPT_DIR = os.path.dirname(os.path.realpath(sys.argv[0]))

	PDF_DIR = TEMP_DIR + '/pdf'
	ensure_dir(PDF_DIR)

	# copy all files in case there are images or other kinds of included stuff
	copy_tree(PACKAGE_DIR + 'statements/english', PDF_DIR)

	# concat header + problem + footer into a single file
	TEX_FILE = PDF_DIR + '/problem.tex'
	with open(TEX_FILE, 'w') as tfile:
		with open(SCRIPT_DIR + '/tex/header.tex') as header:
			shutil.copyfileobj(header, tfile)
		# fix problem number
		tfile.write(r'\addtocounter{problem}{'+ str(ord(PROBCODE) - ord('A')) +'}')
		with open(PACKAGE_DIR + 'statements/english/problem.tex') as statement:
			shutil.copyfileobj(statement, tfile)
		with open(SCRIPT_DIR + '/tex/footer.tex') as footer:
			shutil.copyfileobj(footer, tfile)

	copyfile(OLYMP_PATH, PDF_DIR + '/olymp.sty')

	texproc = subprocess.Popen(['pdflatex', 'problem.tex'], cwd=PDF_DIR)
	texproc.wait()
	if texproc.returncode != 0:
		sys.exit('ERROR while building latex file. Make sure you have pdflatex installed.')

	copyfile(PDF_DIR + '/problem.pdf', OUTPUT_DIR + '/problem.pdf')	

	rmtree(PDF_DIR)
else:
	statements = os.listdir(PACKAGE_DIR + '/statements/.pdf/english')
	if len(statements) != 1:
		print('WARNING: ' + package_name + ' has multiple statements.')
	for statement in statements:
		copyfile(PACKAGE_DIR + '/statements/.pdf/english/' + statement, OUTPUT_DIR + '/' + statement)

#ZIP the OUTPUT and DELETE Temp
make_archive(OUTPUT_PATH + '/' + package_name + '-domjudge', 'zip', OUTPUT_DIR)
rmtree(PACKAGE_DIR)
if nodelete == False:
	rmtree(OUTPUT_DIR)
