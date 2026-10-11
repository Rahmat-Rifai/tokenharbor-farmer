from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt
from rich import box

from config_loader import load_config
from tor_manager import is_port_open, ensure_tor_running, rotate_tor_ip
from th_auto_register import register_one
from th_tor_farm import load_state, save_state, run_farm
from inject_th_kv import inject_9router
from th_preflight import run_preflight

console = Console()

BANNER = """
[bold cyan]
 ████████╗ ██████╗ ██╗  ██╗███████╗███╗   ██╗██╗  ██╗ █████╗ ██████╗ ██████╗  ██████╗ ██████╗
 ╚══██╔══╝██╔═══██╗██║ ██╔╝██╔════╝████╗  ██║██║ ██╔╝██╔══██╗██╔══██╗██╔══██╗██╔═══██╗██╔══██╗
    ██║   ██║   ██║█████╔╝ █████╗  ██╔██╗ ██║█████╔╝ ███████║██████╔╝██████╔╝██║   ██║██████╔╝
    ██║   ██║   ██║██╔═██╗ ██╔══╝  ██║╚██╗██║██╔═██╗ ██╔══██║██╔══██╗██╔═══╝ ██║   ██║██╔══██╗
    ██║   ╚██████╔╝██║  ██╗███████╗██║ ╚████║██║  ██║██║  ██║██║  ██║██║     ╚██████╔╝██║  ██║
    ╚═╝    ╚═════╝ ╚═╝  ╚═╝╚══════╝╚═╝  ╚═══╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝     ╚═════╝ ╚═╝  ╚═╝
[/bold cyan]
[bold green]TokenHarbor Farmer • Free Models • 9Router Inject[/bold green]
[dim]Tor IP rotation • Multi Email • DeepSeek V4.1 Flash Free[/dim]
"""


def main():
    while True:
        console.clear()
        console.print(BANNER, justify="center")
        cfg = load_config()
        tor_ok = is_port_open(cfg.get("tor_socks_port", 9050))
        state = load_state()

        status_text = (
            f"  🔥 Tor (9050): {'[green]READY[/green]' if tor_ok else '[yellow]STOPPED (auto-launch on farm)[/yellow]'}\n"
            f"  ✉️ Email Provider: [cyan]{cfg.get('mail_provider')}[/cyan]\n"
            f"  🔒 Model Lock: [magenta]{cfg.get('default_model')}[/magenta]\n"
            f"  📦 Akun Tersimpan: [bold white]{len(state.get('accounts', []))}[/bold white]"
        )
        console.print(Panel(status_text, title="[bold]Status Sistem[/bold]", box=box.ROUNDED))

        table = Table(title="[bold]MENU PILIHAN[/bold]", box=box.DOUBLE_EDGE, style="cyan")
        table.add_column("No", style="bold yellow", width=4)
        table.add_column("Aksi", style="bold white")
        table.add_column("Keterangan", style="dim")
        table.add_row("1", "Register 1 Akun", "Signup + verify + consent + key + inject 9Router")
        table.add_row("2", "Batch Farm (N Akun)", "Farm massal otomatis dengan rotasi Tor IP")
        table.add_row("3", "Preflight Check", "Diagnosa kelengkapan sistem, Tor, & DB 9Router")
        table.add_row("4", "Rotasi Tor IP (Manual)", "Kirim signal NEWNYM ke Tor")
        table.add_row("5", "Lihat Daftar Akun", "Tampilkan akun yang sudah tersimpan")
        table.add_row("0", "Keluar", "Tutup aplikasi")
        console.print(table)

        pilihan = Prompt.ask("Pilih menu", choices=["1", "2", "3", "4", "5", "0"], default="1")
        if pilihan == "0":
            break
        elif pilihan == "1":
            ensure_tor_running()
            acct, err = register_one(cfg)
            if acct:
                console.print(f"[green]✓ Registrasi Berhasil![/green] {acct['email']}")
                injected, msg = inject_9router(acct["api_key"], acct["email"], cfg)
                console.print(f"9Router: {'[green]INJECTED[/green]' if injected else '[red]FAILED[/red]'} ({msg})")
                acct["injected"] = injected
                state["accounts"].append(acct)
                save_state(state)
            else:
                console.print(f"[red]✗ Gagal:[/red] {err}")
            Prompt.ask("\nTekan Enter untuk kembali")
        elif pilihan == "2":
            n = IntPrompt.ask("Jumlah akun target", default=5)
            run_farm(n)
            Prompt.ask("\nTekan Enter untuk kembali")
        elif pilihan == "3":
            run_preflight()
            Prompt.ask("\nTekan Enter untuk kembali")
        elif pilihan == "4":
            ok = rotate_tor_ip()
            console.print(f"Tor rotation: {'[green]SUCCESS[/green]' if ok else '[red]FAILED[/red]'}")
            Prompt.ask("\nTekan Enter untuk kembali")
        elif pilihan == "5":
            t = Table(title="Akun Tersimpan")
            t.add_column("Email", style="cyan")
            t.add_column("API Key", style="dim")
            t.add_column("Verified", style="green")
            t.add_column("Injected", style="yellow")
            for a in state.get("accounts", []):
                t.add_row(
                    a.get("email", ""),
                    (a.get("api_key", "")[:18] + "...") if a.get("api_key") else "-",
                    "Y" if a.get("verified") else "N",
                    "Y" if a.get("injected") else "N",
                )
            console.print(t)
            Prompt.ask("\nTekan Enter untuk kembali")


if __name__ == "__main__":
    main()
