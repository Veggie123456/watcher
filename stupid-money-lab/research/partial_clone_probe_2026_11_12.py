"""Controlled local Git mechanism probe; never touches the research repository."""
import pathlib,tempfile,subprocess,json,os,time,hashlib,sys

def run(where, args, env=None, data=None):
 r=subprocess.run(['git','-c','user.name=Probe','-c','user.email=probe@example.invalid',*args],cwd=where,env=env,input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
 if r.returncode:raise RuntimeError('local probe failed at '+args[0]+': '+r.stderr.decode()[:500])
 return r.stdout.decode().strip()

def objects(repo):
 return set(run(repo,['cat-file','--batch-all-objects','--batch-check=%(objectname)']).splitlines())

results=[]
with tempfile.TemporaryDirectory(prefix='sm-partial-clone-probe-') as directory:
 root=pathlib.Path(directory);bare=root/'remote.git';seed=root/'seed';seed.mkdir()
 run(root,['init','--bare',str(bare)]);run(bare,['config','uploadpack.allowFilter','true'])
 run(seed,['init','-b','main']);(seed/'stupid-money-lab').mkdir();(seed/'stupid-money-lab'/'state.json').write_text('{"old":1}')
 payload=os.urandom(2*1024*1024);(seed/'unrelated.bin').write_bytes(payload)
 run(seed,['add','.']);run(seed,['commit','-m','initial']);run(seed,['remote','add','origin',str(bare)]);run(seed,['push','origin','main'])
 old_blob=run(seed,['rev-parse','HEAD:unrelated.bin']);original_head=run(seed,['rev-parse','HEAD'])
 for label,option in [('normal',[]),('missing_ok',['--missing-ok'])]:
  repo=root/label;run(root,['clone','--filter=blob:none','--no-checkout','--branch','main',bare.as_uri(),str(repo)])
  before=objects(repo);assert old_blob not in before
  env={**os.environ,'GIT_INDEX_FILE':str(root/(label+'.index')),'GIT_TRACE2_EVENT':str(root/(label+'.trace'))}
  run(repo,['read-tree','HEAD'],env);new_blob=run(repo,['hash-object','-w','--stdin'],data=b'{"observed":2}')
  run(repo,['update-index','--index-info'],env,data=('100644 '+new_blob+'\tstupid-money-lab/state.json\n').encode())
  new_blob_present_before_tree = new_blob in objects(repo)
  assert old_blob not in objects(repo)
  trace_before = len(pathlib.Path(env['GIT_TRACE2_EVENT']).read_text().splitlines())
  started=time.monotonic();tree=run(repo,['write-tree',*option],env);duration=time.monotonic()-started
  trace=[json.loads(x) for x in pathlib.Path(env['GIT_TRACE2_EVENT']).read_text().splitlines()[trace_before:]]
  fetches=[x for x in trace if x.get('event')=='child_start' and 'fetch' in x.get('argv',[])]
  after=objects(repo);commit=run(repo,['commit-tree',tree,'-p',original_head,'-m','probe'],env)
  run(repo,['push','origin',commit+':refs/heads/probe-'+label]);run(bare,['fsck','--full','--no-reflogs'])
  content=subprocess.check_output(['git','show','probe-'+label+':unrelated.bin'],cwd=bare)
  assert content==payload;assert run(bare,['show','probe-'+label+':stupid-money-lab/state.json'])=='{"observed":2}'
  assert run(bare,['rev-parse','main'])==original_head
  results.append({'variant':label,'gitVersion':run(repo,['--version']),'coldPartialClone':True,'unchangedBlobAbsentBefore':True,'unchangedBlobPresentAfterWriteTree':old_blob in after,'writeTreeDurationSeconds':duration,'lazyFetchChildrenDuringWriteTree':len(fetches),'newBlobLocallyPresentBeforeTree':new_blob_present_before_tree,'remoteFsckPassed':True,'unrelatedContentSha256':hashlib.sha256(content).hexdigest(),'frozenStateExactAfterPush':True,'remoteMainUnchanged':True})
report={'protocol':'local-partial-clone-mechanism-probe-v1','results':results,'scope':'Two controlled local file:// partial clones on Git2.52.0; not production network or original60second timeout reproduction; no production option changed.','primaryDocumentation':'https://git-scm.com/docs/git-write-tree.html'}
if len(sys.argv)>1: pathlib.Path(sys.argv[1]).write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
