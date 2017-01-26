#!/usr/bin/env python

from re import sub
from sys import argv,exit
from os import system,getenv,path
from time import clock,time

which = int(argv[1])
sname = argv[0]
argv=[]

import ROOT as root
from PandaCore.Tools.Misc import *
from PandaCore.Tools.Load import *
import PandaCore.Tools.ConfigBuilding as cb
import PandaAnalysis.Tagging.cfg_v8 as tagcfg

now = int(time.time())
Load('PandaAnalysisFlat','PandaAnalyzer')

def copy_local(long_name):
	eosPath = 'root://eoscms.cern.ch//store/user/snarayan'
	eosEXOPath = 'root://eoscms.cern.ch//store/group/phys_exotica'
	cernboxPath = 'root://eosuser//eos/user/s/snarayan'
	cernboxBPath = 'root://eosuser//eos/user/b/bmaier'
	full_path = sub(r'\${CERNBOXB}',cernboxBPath,
			sub(r'\${CERNBOX}',cernboxPath,
				sub(r'\${EOS}',eosPath,
					sub(r'\${EOS2}',eosEXOPath,long_name))))
	PInfo(sname,full_path)

	panda_id = int(long_name.split('/')[-1].split('_')[-1].replace('.root',''))
	input_name = 'input_%i.root'%panda_id

	# xrdcp if remote, copy if local
	if 'root://' in full_path:
		system('xrdcp %s %s'%(full_path,input_name))
	else:
		system('cp %s %s'%(full_path,input_name))

	if path.isfile(input_name):
		PInfo(sname+'.copy_local','Successfully copied to %s'%(input_name))
		return input_name
	else:
		PError(sname+'.copy_local','Failed to copy %s'%input_name)
		return None


def fn(input_name,isData):
	start=clock()
	
	PInfo(sname+'.fn','Starting to process '+input_name)
	# now we instantiate and configure the analyzer
	skimmer = root.PandaAnalyzer()
	skimmer.isData=isData
	skimmer.SetFlag('firstGen',False)
	skimmer.SetFlag('puppi',False)
	skimmer.SetPreselectionBit(root.PandaAnalyzer.kRecoil)
	#skimmer.SetPreselectionBit(root.PandaAnalyzer.kMonotop)
	processType=root.PandaAnalyzer.kNone
	if not isData:
		if 'ST_' in full_path:
			processType=root.PandaAnalyzer.kTop
		elif 'ZJets' in full_path or 'DY' in full_path:
			processType=root.PandaAnalyzer.kZ
		elif 'WJets' in full_path:
			processType=root.PandaAnalyzer.kW
		elif 'GJets' in full_path:
			processType=root.PandaAnalyzer.kA
		elif 'TTJets' in full_path or 'TT_' in full_path:
			processType=root.PandaAnalyzer.kTT
	skimmer.processType=processType 

	# read the inputs
	try:
		fin = root.TFile.Open(input_name)
		tree = fin.FindObjectAny("events")
		infotree = fin.FindObjectAny("all")
	except:
		PError(sname+'.fn','Could not read %s'%input_name)
		return False # file open error => xrootd?

	output_name = input_name.replace('input','output')
	skimmer.SetDataDir(getenv('CMSSW_BASE')+'/src/PandaAnalysis/data/')
	skimmer.SetOutputFile(output_name)
	skimmer.Init(tree,infotree)

	# run and save output
	skimmer.Run()
	skimmer.Terminate()

	ret = path.isfile(output_name)
	if ret:
		PInfo(sname+'.fn','Successfully created %s in %.2f sec'%(output_name,(clock()-start)/1000.))
	else:
		PError(sname+'.fn','Failed in creating %s!'%(output_name))


def hadd(good_inputs):
	good_outputs = ' '.join([x.replace('input','output') for x in good_inputs])
	cmd = 'hadd -f output.root ' + good_outputs
	ret = system(cmd)	
	if not ret:
		PInfo(sname+'.hadd','Merging exited with code %i'%ret)
	else:
		PError(sname+'.hadd','Merging exited with code %i'%ret)


def add_bdt():
	# now run the BDT
	Load('Learning','TMVABranchAdder')
	ba = root.TMVABranchAdder()
	ba.treename = 'events'
	ba.defaultValue = -1.2
	ba.presel = 'fj1ECFN_2_4_20>0'
	for v in tagcfg.variables:
		ba.AddVariable(v[0],v[2])
	for v in tagcfg.formulae:
		ba.AddFormula(v[0],v[2])
	for s in tagcfg.spectators:
		ba.AddSpectator(s[0])
	ba.BookMVA('top_ecf_bdt',getenv('CMSSW_BASE')+'/src/PandaAnalysis/data/trainings/top_ecfbdt_v8_BDT.weights.xml')
	ba.RunFile('output.root')


def stageout(outdir,outfilename):
	mvargs = 'mv $PWD/output.root %s/%s'%(outdir,outfilename)
	PInfo(sname,mvargs)
	ret = system(mvargs)
	system('rm *.root')
	if not ret:
		PInfo(sname+'.stageout','Move exited with code %i'%ret)
	else:
		PError(sname+'.stageout','Move exited with code %i'%ret)
	return ret


def write_lock(outdir,outfilename,processed):
	flock = open(outdir+'/locks/'+outfilename.replace('.root','.lock'),'w')
	for k,v in processed.iteritems():
		flock.write(v+'\n')
	flock.close()


if __name__ == "__main__":
	sample_list = read_sample_config('local.cfg',as_dict=False)
	to_run = sample_list[which]
	outdir = 'XXXX' # will be replaced when building the job
	outfilename = to_run.name+'_%i.root'%(now)
	processed = {}

	for f in to_run.files:
		input_name = copy_local(f)
		if input_name:
			success = fn(input_name,(to_run.dtype!='MC'))
			if success:
				processed[input_name] = f
	
	if len(processed)==0:
		exit(1)

	hadd(list(processed))
	add_bdt()
	stageout(outdir,outfilename)
	write_lock(outdir,outfilename,processed)

	exit(0)