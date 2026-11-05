"""Native link-import dialogs and callbacks, without REAPER or network."""
from pathlib import Path
import pytest

LuaRuntime = pytest.importorskip("lupa.lua54").LuaRuntime
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def ui():
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute('''
      allowed = true
      completed = 0
      requested = {}
      input = "https://youtu.be/abcdefghijk"
      reaper = {
        GetResourcePath=function() return "/temporary/resources" end,
        RecursiveCreateDirectory=function() end,
        GetUserInputs=function(title, n, labels, default) return true, input end,
        genGuid=function() return "guid" end,
        ShowMessageBox=function() return 1 end
      }
      ctx = {SEP="/", T=function(k)return k end,
        require_edit=function() return allowed end,
        L={lang=function()return "fr" end, projects_dir=function()return "/projects" end,
           exists=function(path)return not path:match("%.RPP$") end},
        R={STATUS="/status", read=function()return "status" end,
           json_decode=function()return status end,
           json_encode=function(data) request=data; return "JSON" end,
           write_atomic=function()return true end, is_windows=function()return false end,
           shq=function(s)return "'"..s.."'" end},
        newsong={safe=function(s)return s end,ask_title=function()return "My Song" end, clean_title=function(s)return s end,
           complete=function(folder,title,files,single)
             completed=completed+1; completion={folder,title,files[1],single}; return true
           end},
        show_result=function(title,msg,ok) shown=msg end,
        start_cli=function(cmd,label,cb,quiet)
          callback=cb; requested[#requested+1]=request; command=cmd; return true
        end
      }
    ''')
    importer = lua.eval(f'dofile([[{ROOT / "reaper/ReaCue_import.lua"}]])(ctx)')
    return lua, importer


def test_link_inspection_then_passage_then_project_without_analysis(ui):
    lua, importer = ui
    g = lua.globals()
    assert importer.start()
    assert g.requested[1].operation == "inspect"
    assert "https://" not in g.command and "--job" in g.command
    lua.execute('''
      status={import_audio={operation="inspect",url="https://youtu.be/abcdefghijk",title="Demo",duration=120}}
      input="0:10,1:00,best"
      callback("done","Metadata ready")
    ''')
    assert g.requested[2].operation == "download"
    assert g.requested[2].start == 10 and g.requested[2]["end"] == 60
    assert g.requested[2].format == "best"
    assert g.completed == 0
    lua.execute('''
      status={import_audio={operation="download",file="/projects/My Song/My Song.ogg",folder="/projects/My Song",title="My Song"}}
      callback("done","Audio ready")
    ''')
    assert g.completed == 1
    assert list(g.completion.values()) == ["/projects/My Song", "My Song", "My Song.ogg", True]


def test_performance_lock_blocks_import_and_late_project_creation(ui):
    lua, importer = ui
    g = lua.globals()
    g.allowed = False
    assert not importer.start() and len(g.requested) == 0
    g.allowed = True
    g.input = "0,60,best"
    importer.download(lua.table_from({"title": "Demo", "duration": 60, "url": "https://youtu.be/abcdefghijk"}))
    lua.execute('''
      allowed=false
      status={import_audio={operation="download",file="/audio.ogg",folder="/projects/Demo",title="Demo"}}
      callback("done","Audio ready")
    ''')
    assert g.completed == 0


def test_cancelled_job_does_not_create_project(ui):
    lua, importer = ui
    importer.start()
    lua.execute('callback("cancelled", "Import annulé")')
    assert lua.globals().completed == 0 and lua.globals().shown == "Import annulé"


def test_time_input(ui):
    _, importer = ui
    assert importer.seconds("2:03.5") == 123.5
    assert importer.seconds("125") == 125
    assert importer.seconds("2:75") is None


def test_resume_completed_download_opens_existing_project_without_reimport(ui):
    lua, importer = ui
    data = lua.table_from({"operation": "download", "file": "/projects/Demo/Demo.ogg", "folder": "/projects/Demo", "title": "Demo"})
    assert importer.resume(data)
    assert lua.globals().completed == 1
    lua.execute('''
      ctx.L.exists=function()return true end
      ctx.refresh=function()end
      ctx.goto_tab=function()end
      reaper.Main_OnCommand=function()opened=true end
      reaper.Main_openProject=function(path)opened_path=path end
    ''')
    assert importer.resume(data)
    assert lua.globals().completed == 1
    assert lua.globals().opened_path == "noprompt:/projects/Demo/Demo.RPP"
