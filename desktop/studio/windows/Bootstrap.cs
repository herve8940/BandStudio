using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;
class Bootstrap {
    [STAThread] static void Main() {
        string root=AppDomain.CurrentDomain.BaseDirectory;
        string logs=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"BandStudio","Logs");
        string log=Path.Combine(logs,"startup.log");
        try {
            Directory.CreateDirectory(logs);
            var info=new ProcessStartInfo(Path.Combine(root,"engine","python","python.exe"),"\""+Path.Combine(root,"engine","windows","launcher.py")+"\"");
            info.WorkingDirectory=root; info.UseShellExecute=false; info.CreateNoWindow=true; info.RedirectStandardOutput=true; info.RedirectStandardError=true;
            info.EnvironmentVariables["PYTHONUTF8"]="1";
            using(var writer=new StreamWriter(log,false)) {
                object gate=new object();
                using(var process=new Process()) {
                    process.StartInfo=info;
                    process.OutputDataReceived+=(s,e)=>{if(e.Data!=null)lock(gate){writer.WriteLine(e.Data);writer.Flush();}};
                    process.ErrorDataReceived+=(s,e)=>{if(e.Data!=null)lock(gate){writer.WriteLine(e.Data);writer.Flush();}};
                    process.Start();process.BeginOutputReadLine();process.BeginErrorReadLine();process.WaitForExit();
                    if(process.ExitCode!=0)MessageBox.Show("BandStudio n’a pas pu démarrer.\n\nLe journal de diagnostic est ici :\n"+log,"BandStudio",MessageBoxButtons.OK,MessageBoxIcon.Error);
                }
            }
        } catch(Exception e) {MessageBox.Show(e.Message+"\n\nDécompresse tout le dossier avant de lancer BandStudio.","BandStudio",MessageBoxButtons.OK,MessageBoxIcon.Error);}
    }
}
