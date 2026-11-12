"""Local-only integrity gate probe. Does not import or change the live collector."""
import pathlib,tempfile,subprocess,json,os,hashlib,sys,time,re


def git(where,args,env=None,data=None):
 r=subprocess.run(['git','-c','user.name=Probe','-c','user.email=probe@example.invalid',*args],cwd=where,env=env,input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
 if r.returncode:raise RuntimeError('local probe command failed: '+args[0])
 return r.stdout.decode().strip()


def verify_changed_blobs(repo,expected):
 """Only caller-frozen blob IDs and byte lengths; no lazy fetching is allowed."""
 if not expected or any(not re.fullmatch('[0-9a-f]{40}',oid) or size<0 for oid,size in expected.items()):
  return False
 output=git(repo,['--no-lazy-fetch','cat-file','--batch-check=%(objectname) %(objecttype) %(objectsize)'],data=('\n'.join(expected)+'\n').encode())
 records=output.splitlines()
 if len(records)!=len(expected):return False
 for oid,row in zip(expected,records):
  fields=row.split()
  if len(fields)!=3 or fields[0]!=oid or fields[1]!='blob' or fields[2]!=str(expected[oid]):return False
 return True


def run_probe():
 with tempfile.TemporaryDirectory(prefix='sm-guarded-tree-probe-') as directory:
  root=pathlib.Path(directory);bare=root/'remote.git';seed=root/'seed';seed.mkdir()
  git(root,['init','--bare',str(bare)]);git(bare,['config','uploadpack.allowFilter','true'])
  git(seed,['init','-b','main']);(seed/'unchanged').write_bytes(b'unchanged remote payload'*2000);(seed/'state').write_text('old')
  git(seed,['add','.']);git(seed,['commit','-m','seed']);git(seed,['remote','add','origin',str(bare)]);git(seed,['push','origin','main'])
  baseline=git(seed,['rev-parse','HEAD']);unchanged=git(seed,['rev-parse','HEAD:unchanged'])
  repo=root/'runner';git(root,['clone','--filter=blob:none','--no-checkout','--branch','main',bare.as_uri(),str(repo)])
  local_before=set(git(repo,['cat-file','--batch-all-objects','--batch-check=%(objectname)']).splitlines());assert unchanged not in local_before
  payload=b'{"frozenGeneration":2}';new_blob=git(repo,['hash-object','-w','--stdin'],data=payload)
  trace=root/'guard-trace';env={**os.environ,'GIT_TRACE2_EVENT':str(trace)}
  def check(expected):
   # Guard function uses --no-lazy-fetch; setting Trace2 in the parent environment
   # records any unexpected child fetch without exposing the trace in the report.
   previous=os.environ.get('GIT_TRACE2_EVENT');os.environ['GIT_TRACE2_EVENT']=str(trace)
   try:return verify_changed_blobs(repo,expected)
   finally:
    if previous is None:os.environ.pop('GIT_TRACE2_EVENT',None)
    else:os.environ['GIT_TRACE2_EVENT']=previous
  assert check({new_blob:len(payload)})
  absent_payload=b'never written into this object database'
  absent=hashlib.sha1(b'blob '+str(len(absent_payload)).encode()+b'\0'+absent_payload).hexdigest()
  rejected_missing=not check({absent:len(absent_payload)})
  rejected_mixed=not check({new_blob:len(payload),absent:len(absent_payload)})
  rejected_tree=not check({git(repo,['rev-parse','HEAD^{tree}']):len(payload)})
  rejected_wrong_size=not check({new_blob:len(payload)+1})
  assert rejected_missing and rejected_mixed and rejected_tree and rejected_wrong_size
  trace_rows=[json.loads(x) for x in trace.read_text().splitlines()]
  fetches=sum(x.get('event')=='child_start' and 'fetch' in x.get('argv',[]) for x in trace_rows)
  assert fetches==0
  private_env={**os.environ,'GIT_INDEX_FILE':str(root/'private-index')}
  git(repo,['read-tree','HEAD'],private_env)
  git(repo,['update-index','--index-info'],private_env,data=('100644 '+new_blob+'\tstate\n').encode())
  tree=git(repo,['write-tree','--missing-ok'],private_env)
  local_after=set(git(repo,['cat-file','--batch-all-objects','--batch-check=%(objectname)']).splitlines());assert unchanged not in local_after
  commit=git(repo,['commit-tree',tree,'-p',baseline,'-m','local guarded candidate'],private_env)
  git(repo,['push','origin',commit+':refs/heads/local-guard-probe']);git(bare,['fsck','--full','--no-reflogs'])
  assert git(bare,['show','local-guard-probe:state'])==payload.decode()
  assert git(bare,['rev-parse','local-guard-probe:unchanged'])==unchanged
  assert git(bare,['rev-parse','main'])==baseline
  return {'protocol':'local-guarded-tree-candidate-probe-v1','gitVersion':git(repo,['--version']),
          'scope':'Controlled local file:// cold partial clone only; live collector unchanged; not production root-cause or latency proof.',
          'validFrozenBlobAccepted':True,'missingEditedBlobRejectedBeforeTreeCreation':rejected_missing,
          'mixedValidAndMissingEditedBlobsRejectedBeforeTreeCreation':rejected_mixed,
          'nonBlobEditedObjectRejectedBeforeTreeCreation':rejected_tree,'wrongEditedBlobSizeRejectedBeforeTreeCreation':rejected_wrong_size,
          'guardLazyFetchChildren':fetches,'unchangedBlobAbsentBeforeAndAfterTree':True,
          'validCandidateRemoteFsckPassed':True,'frozenStateExactAfterPush':True,'unrelatedObjectRetained':True,'remoteMainUnchanged':True,
          'candidateActivationAllowed':False,'activationGate':'Actual production fetch-child evidence plus integrated collector regression tests still required.'}


if __name__=='__main__':
 result=run_probe()
 if len(sys.argv)>1:pathlib.Path(sys.argv[1]).write_text(json.dumps(result,indent=2))
 print(json.dumps(result,indent=2))
