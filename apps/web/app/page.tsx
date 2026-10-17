import { Button, CoverCard, RankRow, RoomCard, SectionHeader, Tag, ZumiOrb } from "@zumi/ui";
import { ThemeToggle } from "./theme-toggle";

/* Mock data until the API exists. Shapes mirror packages/format and the Supabase tables. */
const weekday = [
  { title: "Winter Passing By", meta: "Haeun", up: true, mark: { text: "NEW" }, sticker: "Released today", readingNow: 14 },
  { title: "Nanomachine", meta: "Hyun Jeolmu · Han Jungwol", up: true, readingNow: 6 },
  { title: "Strongest Legend Kang Haehyo", meta: "Choi Byungyeol", up: true },
  { title: "Kubera", meta: "Currygom", up: true },
  { title: "Almost Forty", meta: "Seokons", mark: { text: "15+", variant: "mark" as const } },
];
const picks = ["Parenting Diary", "Eating Life 2", "Science Survival", "Turns Out, Boyfriend", "Kindergarten Guna"];
const genres = ["Romance", "Fantasy", "Action", "Slice of life", "Thriller", "Comedy", "Historical", "Drama", "Emotion", "Sports"];
const ranking = [
  { title: "Starry Shop", meta: "Heono · 14 in rooms", trend: 2 },
  { title: "Nanomachine", meta: "Hyun Jeolmu · 11", up: true, trend: -1 },
  { title: "Return of the Mount Hua Sect", meta: "ARCHE · LICO · 9", trend: 5 },
  { title: "World Apocalypse Legend", meta: "Punchkick · 8", up: true },
  { title: "Barbarian in the Game World", meta: "Midnight Studio · 7" },
];
const rooms = [
  { title: "Winter Passing By · Ep. 7", readers: ["orange", "sky", "lime"], panel: 12, panelCount: 30, status: "Started 4 min ago" },
  { title: "Nanomachine · Ep. 112", readers: ["lilac", "coral"], panel: 3, panelCount: 41, status: "Started just now" },
  { title: "Kubera · Ep. 530", readers: ["yellow", "mint", "pink", "sky", "orange", "lime", "coral"], panel: 28, panelCount: 36, status: "Almost full" },
  { title: "Almost Forty · Ep. 1", readers: ["sky"], panel: 1, panelCount: 24, status: "Looking for readers" },
] as const;
const tags = ["#romance", "#fantasy", "#action", "#slice-of-life", "#thriller", "#comedy", "#martial-arts", "#drama", "#sports", "#from-novel", "#school", "#office", "#xr-scenes", "#360", "#contest-2026", "#regression", "#isekai", "#idol"];

export default function Home() {
  return (
    <main className="mx-auto max-w-[1180px] px-4 pb-10 grid gap-8">
      {/* header */}
      <header className="flex items-center gap-3.5 pt-3.5">
        <a href="/" className="flex items-center gap-2 font-display font-extrabold text-2xl tracking-[0.02em]">
          <ZumiOrb size={22} mood="happy" label="Zumi" />
          ZUMI
        </a>
        <nav className="ml-1.5 flex gap-2.5 text-lg font-medium text-text-faint">
          <a href="#">Series</a>
          <a href="#">Rooms</a>
        </nav>
        <span className="flex-1" />
        <div className="flex w-[340px] max-w-full items-center justify-between rounded-pill border border-hairline-strong px-3.5 py-1.5 text-text-faint">
          <span>Search by title or creator</span>
          <span aria-hidden>⌕</span>
        </div>
        <Button variant="ghost" size="sm">
          Log in
        </Button>
        <ThemeToggle />
      </header>

      {/* tab bar */}
      <nav className="flex items-center gap-5 border-b border-hairline pb-2.5">
        <span className="grid size-7 place-items-center rounded-[5px] bg-accent font-display font-extrabold text-lg text-text-on-accent">Z</span>
        <a className="text-lg font-bold">Series</a>
        <a className="relative text-lg font-bold">
          Rooms
          <span className="absolute -right-2.5 -top-1.5 grid size-3 place-items-center rounded-pill bg-alert text-[8px] font-extrabold text-white">N</span>
        </a>
        <a className="text-lg font-bold text-text-dim">Rising</a>
        <a className="text-lg font-bold text-text-dim">Challenge</a>
        <a className="text-lg font-bold text-text-dim">My page</a>
        <span className="flex-1" />
        <Button variant="cta" size="sm">
          Creator's
        </Button>
      </nav>

      {/* weekday row */}
      <section className="grid gap-3.5">
        <SectionHeader title="Wednesday series" more="All Wednesday series">
          <span>Popular</span>
          <span>Updated</span>
          <b className="text-accent">Reading now</b>
          <span>Rating</span>
        </SectionHeader>
        <div className="grid grid-cols-3 gap-4 md:grid-cols-5">
          {weekday.map((c) => (
            <CoverCard key={c.title} {...c} href="#" />
          ))}
        </div>
      </section>

      {/* banner */}
      <div className="flex items-center justify-center gap-5 rounded-panel bg-room-banner px-6 py-4">
        <ZumiOrb size={50} mood="wow" bob />
        <div>
          <h3 className="font-display font-extrabold text-3xl leading-[1.05]">Creator contest, season 2</h3>
          <p className="mt-0.5 font-bold text-accent">Enter now and read your series in XR</p>
        </div>
        <Button variant="cta" className="ml-3">
          Enter
        </Button>
      </div>

      {/* picks */}
      <section className="grid gap-3.5">
        <SectionHeader title="Only the hottest slice-of-life series, picked for you" more="More slice-of-life" />
        <div className="-mt-1.5 flex flex-wrap gap-2.5 text-sm text-text-dim">
          {genres.map((g) => (
            <span key={g} className={g === "Slice of life" ? "font-bold text-accent" : ""}>
              {g}
            </span>
          ))}
        </div>
        <div className="grid grid-cols-3 gap-4 md:grid-cols-[repeat(5,minmax(0,1fr))_1.7fr]">
          {picks.map((title, i) => (
            <div key={title} className="relative">
              <CoverCard title={title} up={i !== 3} href="#" />
              <span className="pointer-events-none absolute -left-1 top-[112px] font-display font-extrabold text-numeral leading-none text-text-default [paint-order:stroke_fill] [-webkit-text-stroke:3px_var(--color-room-field)]">
                {i + 1}
              </span>
            </div>
          ))}
          <div className="col-span-3 md:col-span-1 grid content-center gap-1.5 rounded-panel border border-hairline bg-room-raised p-5 text-center">
            <h4 className="font-display font-extrabold text-3xl leading-[1.05]">Read together tonight</h4>
            <p className="text-text-dim">Rooms open every evening. Bring a friend, or meet one.</p>
            <Button variant="cta" className="mx-auto mt-2">
              Find a room
            </Button>
          </div>
        </div>
      </section>

      {/* main + rail */}
      <div className="grid gap-7 md:grid-cols-[minmax(0,1fr)_300px] items-start">
        <div className="grid gap-8">
          <section className="grid gap-3.5">
            <SectionHeader title="Rooms open now" more="All rooms" />
            <div className="grid gap-3.5 sm:grid-cols-2">
              {rooms.map((r) => (
                <RoomCard key={r.title} title={r.title} readers={r.readers.map((hue, i) => ({ id: String(i), hue }))} panel={r.panel} panelCount={r.panelCount} status={r.status} />
              ))}
            </div>
          </section>

          <section className="grid gap-3.5">
            <SectionHeader title="Fresh updates, daily+" more="More daily+" />
            <div className="grid grid-cols-3 gap-4 md:grid-cols-5">
              {["The Fiancé Prince Is Hiding", "Difficult Husband", "Lover Roulette", "Ain", "Safe Relationship"].map((t) => (
                <CoverCard key={t} title={t} meta="Updated today" up href="#" />
              ))}
            </div>
          </section>

          <section className="grid gap-3.5">
            <SectionHeader title="Series shortcuts" />
            <div className="flex flex-wrap gap-2">
              {tags.map((t) => (
                <Tag key={t} variant="hash">
                  {t}
                </Tag>
              ))}
            </div>
          </section>
        </div>

        <aside className="grid gap-7">
          <section className="grid gap-3">
            <SectionHeader title="Reading now">
              <span className="ml-auto flex gap-2 text-xs">
                <b className="text-text-default">All</b>
                <span>Female</span>
                <span>Male</span>
              </span>
            </SectionHeader>
            {ranking.map((r, i) => (
              <RankRow key={r.title} rank={i + 1} {...r} href="#" />
            ))}
          </section>
          <div className="grid gap-1 rounded-panel border border-hairline p-4">
            <h4 className="font-display font-extrabold text-xl leading-[1.1]">Working creator?</h4>
            <p className="font-bold text-accent">Propose your next series</p>
          </div>
          <section className="grid gap-3">
            <SectionHeader title="Notices" more="More" />
            <ul className="grid gap-1.5 text-sm text-text-dim">
              <li className="text-text-default">Creator contest season 2: submission guide</li>
              <li>Quest 3 app build 0.4 is on the store</li>
              <li>Room capacity raised to 8</li>
              <li>Scheduled maintenance Oct 20, 02:00 to 04:00</li>
            </ul>
          </section>
        </aside>
      </div>

      <footer className="grid gap-3 border-t border-hairline pt-3.5 text-xs text-text-faint">
        <div className="flex flex-wrap gap-3.5 text-sm text-text-dim">
          <b className="text-text-default">Series</b>
          <b className="text-text-default">Rooms</b>
          <b className="text-text-default">Creators</b>
          <span>Help center</span>
          <span>Terms</span>
          <span>Privacy</span>
        </div>
        <p>© Zumi. Every series remains the property of its creator.</p>
      </footer>
    </main>
  );
}
