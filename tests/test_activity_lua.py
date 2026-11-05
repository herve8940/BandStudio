"""The durable task view and reopened native window, with simulated REAPER."""
import json
from pathlib import Path
import time

import pytest
import test_reacue_window as W


@pytest.fixture
def window(tmp_path):
    concert=W.TL.make_concert(tmp_path)
    lua,g=W.rt(concert)
    W.open_window(lua,g)
    lua.execute('REACUE_CTX.R.pid_alive=function(pid) return pid==123 end')
    return lua,g,g.REACUE_CTX


def write_job(ctx, **updates):
    data={"id":"active", "cmd":"prepare", "launch_command":"prepare", "project":ctx.proj_file,
          "state":"running", "pid":123, "time":time.time(), "started":time.time()}
    data.update(updates)
    p=Path(ctx.R.DIR)/'jobs'/f'{data["id"]}.json'
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(data))
    Path(ctx.R.STATUS).write_text(json.dumps(data))
    return data


def test_reopened_window_follows_matching_worker_without_launch(window):
    lua,g,ctx=window
    write_job(ctx)
    before=len(g.state.shell)
    g.state.t += 4  # recovery probes are throttled to three seconds
    W.frame(lua,g)
    assert ctx.job.id=='active' and ctx.job.recovered
    assert len(g.state.shell)==before
    write_job(ctx,state='done',message='Prepared')
    W.frame(lua,g)
    assert ctx.job is None


def test_other_project_job_visible_without_attaching_and_cancel_path_is_local(window):
    lua,g,ctx=window
    data=write_job(ctx,project='/other/project.RPP',cmd='import-audio',cancellable=True,cancel_file='/outside.cancel')
    W.frame(lua,g)
    assert ctx.job is None
    rows=ctx.jobs.scan(True)
    assert len(rows)==1 and rows[1].project=='/other/project.RPP'
    assert ctx.jobs.cancel(rows[1])
    assert (Path(ctx.R.DIR)/'jobs/active.cancel').exists()
    assert not ctx.jobs.cancel(lua.table_from({'id':'../outside','cancellable':True}))


def test_activity_translates_tasks_and_reports_dead_worker(window):
    lua,g,ctx=window
    write_job(ctx,pid=456)
    assert ctx.jobs.scan(True)[1].state=='interrupted'
    ctx.overlay='jobs'
    W.frame(lua,g)
    texts=W.TL.texts(g)
    assert any('Préparation du morceau' in text for text in texts)
    assert any('Interrompu' in text for text in texts)


def test_concert_opens_when_ready_while_extras_remain_tracked(window):
    lua,g,ctx=window
    write_job(ctx,cmd='concert',reported_state='done',message='Concert ready; details are still running')
    lua.execute('''
      completed=0
      REACUE_CTX.job={kind="cli",id="active",cmd="concert",t0=reaper.time_precise(),
        on_done=function(state,message) assert(state=="done"); completed=completed+1 end}
    ''')
    W.frame(lua,g)
    assert g.completed==1 and ctx.job is None
    assert ctx.jobs.scan(True)[1].state=='running'
    g.state.t+=4
    W.frame(lua,g)
    assert g.completed==1 and ctx.job is None
