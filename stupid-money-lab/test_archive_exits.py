import tempfile,pathlib,json,datetime as dt
import genius_copy as g
now='2026-11-05T22:00:00+00:00'
ms=lambda s:dt.datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()*1000
p={'wallet':'0x'+'a'*40,'symbol':'BTC','direction':'long','sourceOpenedAt':'2026-11-05T21:00:00+00:00','legs':[]}
e={'id':99,'coin':'BTC','createdAt':'2026-11-05T21:10:00+00:00','payload':{'wallet':p['wallet'],'side':'LONG','cohort':'GENIUS','action':'CLOSED'}}
s={'geniusCopy':{'positions':{'a':p}}}
with tempfile.TemporaryDirectory() as root:
 path=pathlib.Path(root)/'data/2026-11-05/events.jsonl';path.parent.mkdir(parents=True)
 path.write_text(json.dumps({'kind':'revision','event':dict(e,id=88)})+'\n'+json.dumps({'kind':'first_observation','event':e})+'\n')
 out=g.archived_exit_events(s,pathlib.Path(root),lambda:now,ms,lambda *a:None)
 assert [x['id'] for x in out]==[99] and s['geniusCopy']['archiveExitScan']['exitCardsReviewed']==1
 now='2026-11-05T22:06:00+00:00'
 out=g.archived_exit_events(s,pathlib.Path(root),lambda:now,ms,lambda *a:None)
 assert out[0]['id']==99 and s['geniusCopy']['archiveExitScan']['bytesRead']==0
 p['legs'].append({'eventId':99});now='2026-11-05T22:12:00+00:00'
 assert not g.archived_exit_events(s,pathlib.Path(root),lambda:now,ms,lambda *a:None)
 print('Original-only exit backscan, retained quote-failure retry, incremental cursor and filled-exit dedupe passed')
