"""Chatbot dòng lệnh.

  python -m scholarlens.chat                 # chế độ auto
  python -m scholarlens.chat --mode research

Lệnh trong phiên: /mode chat|research|auto  /focus <paper_id ...>  /unfocus  /add <file.pdf>  /quit
"""
import argparse


def main():
    ap = argparse.ArgumentParser(prog="scholarlens.chat")
    ap.add_argument("--mode", default="auto", choices=["auto", "chat", "research"])
    a = ap.parse_args()
    from ..services import Services

    s = Services.get()
    mode, focus, cid = a.mode, [], None
    print(f"ScholarLens CLI — LLM: {s.llm.name} — {s.db.stats()['papers']} bài. Gõ /quit để thoát.")
    while True:
        try:
            msg = input(f"\n[{mode}{' · focus ' + ','.join(focus) if focus else ''}] Bạn: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not msg:
            continue
        if msg == "/quit":
            break
        if msg.startswith("/mode "):
            mode = msg.split()[1]
            continue
        if msg.startswith("/focus "):
            focus = msg.split()[1:]
            continue
        if msg == "/unfocus":
            focus = []
            continue
        if msg.startswith("/add "):
            with s.ingest_lock:
                r = s.ingest.add_pdf(msg[5:].strip(), log_step=lambda x: print("  ·", x))
            print(f"  => {r.status}: {r.title} {r.reason}")
            if r.paper_id:
                focus = [r.paper_id]
            continue
        print("ScholarLens: ", end="", flush=True)
        for ev in s.chatbot.respond(msg, cid, mode, focus):
            if ev["type"] == "meta":
                cid = ev["conversation_id"]
            elif ev["type"] == "query":
                print(f"\n  (truy vấn: {ev['text']})\n", end="")
            elif ev["type"] == "sources":
                for src in ev["sources"]:
                    print(f"\n  [{src['n']}] {src['title'][:80]} ({src['year']}) – {src['role']}", end="")
                print("\n")
            elif ev["type"] == "token":
                print(ev["text"], end="", flush=True)
        print()


if __name__ == "__main__":
    main()
