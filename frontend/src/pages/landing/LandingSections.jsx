import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import {
  ArrowRight, ClipboardCheck, ShieldAlert, IndianRupee, FileText, Users, Building2, Home,
  HardHat, UserRound, Briefcase, Mail, Phone, MapPin, CheckCircle2,
} from "lucide-react";

const IMG = {
  hero: "https://images.unsplash.com/photo-1527335988388-b40ee248d80c?crop=entropy&cs=srgb&fm=jpg&q=80&w=1600",
  villa: "https://images.unsplash.com/photo-1580587771525-78b9dba3b914?crop=entropy&cs=srgb&fm=jpg&q=80&w=1200",
  tower: "https://images.unsplash.com/photo-1599707254554-027aeb4deacd?crop=entropy&cs=srgb&fm=jpg&q=80&w=1200",
  engineer: "https://images.unsplash.com/photo-1628158088791-89567a8e84ec?crop=entropy&cs=srgb&fm=jpg&q=80&w=1200",
};
export const CONTACT = { email: "civiobuilds@gmail.com", phone: "+91 91080 98446", tel: "+919108098446" };

export function LandingNav() {
  return (
    <header className="fixed inset-x-0 top-0 z-50 border-b border-white/10 bg-[hsl(222_60%_11%)]/80 backdrop-blur-xl">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-3 md:px-8">
        <a href="#top" className="flex items-center gap-2.5" data-testid="landing-logo">
          <span className="rounded-lg bg-white px-2 py-0.5"><img src="/civio-logo.png" alt="CIVIO" className="h-9" /></span>
        </a>
        <nav className="hidden items-center gap-7 text-sm text-white/70 md:flex">
          <a href="#about" className="transition-colors hover:text-white">About</a>
          <a href="#features" className="transition-colors hover:text-white">Platform</a>
          <a href="#workspaces" className="transition-colors hover:text-white">Workspaces</a>
          <a href="#contact" className="transition-colors hover:text-white">Contact</a>
        </nav>
        <div className="flex items-center gap-2">
          <Link to="/login"><Button variant="ghost" className="text-white hover:bg-white/10 hover:text-white" data-testid="landing-signin-btn">Sign in</Button></Link>
          <Link to="/register"><Button className="rounded-full bg-[hsl(222_100%_56%)] hover:bg-[hsl(222_100%_50%)]" data-testid="landing-register-btn">Get started</Button></Link>
        </div>
      </div>
    </header>
  );
}

export function Hero() {
  return (
    <section id="top" className="relative overflow-hidden bg-[hsl(222_60%_11%)] pt-28 text-white md:pt-36">
      <img src={IMG.hero} alt="Steel frame under construction" className="absolute inset-0 h-full w-full object-cover opacity-25" />
      <div className="absolute inset-0 bg-gradient-to-r from-[hsl(222_60%_11%)] via-[hsl(222_60%_11%)]/85 to-transparent" />
      <div className="relative mx-auto grid max-w-7xl gap-12 px-5 pb-20 md:px-8 lg:grid-cols-[1.2fr_1fr] lg:pb-28">
        <div className="animate-fade-up">
          <p className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1 text-xs font-semibold uppercase tracking-widest text-emerald-300">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" /> Your Build, Our Expertise
          </p>
          <h1 className="mt-6 font-heading text-4xl font-extrabold leading-[1.05] sm:text-5xl lg:text-6xl" data-testid="landing-hero-title">
            Every site, every stage,<br /><span className="text-[hsl(222_100%_66%)]">in total clarity.</span>
          </h1>
          <p className="mt-6 max-w-xl text-base text-white/70 md:text-lg">
            CIVIO is the construction project management platform that connects owners, project managers, site engineers and clients — progress, approvals, quality, procurement and reports in one place.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link to="/register"><Button size="lg" className="rounded-full bg-[hsl(222_100%_56%)] px-7 hover:bg-[hsl(222_100%_50%)]" data-testid="hero-register-btn">Register your company <ArrowRight className="h-4 w-4" /></Button></Link>
            <a href="#contact"><Button size="lg" variant="outline" className="rounded-full border-white/30 bg-transparent px-7 text-white hover:bg-white/10 hover:text-white" data-testid="hero-contact-btn">Talk to us</Button></a>
          </div>
          <div className="mt-12 grid max-w-lg grid-cols-3 gap-6 border-t border-white/10 pt-6">
            {[["360°", "Project visibility"], ["4", "Connected roles"], ["100%", "Audit-ready trail"]].map(([v, l]) => (
              <div key={l}><div className="font-heading text-3xl font-bold">{v}</div><div className="text-xs text-white/60">{l}</div></div>
            ))}
          </div>
        </div>
        <HeroCard />
      </div>
    </section>
  );
}

function HeroCard() {
  return (
    <div className="relative hidden animate-fade-up lg:block" style={{ animationDelay: "150ms" }}>
      <img src={IMG.villa} alt="Completed modern villa" className="h-[420px] w-full rounded-3xl object-cover shadow-2xl" />
      <div className="absolute -bottom-6 -left-8 w-72 rounded-2xl border border-white/10 bg-white p-4 text-slate-900 shadow-xl">
        <div className="flex items-center justify-between text-xs font-semibold text-slate-500"><span>Kapoor Residence</span><span className="text-emerald-600">On track</span></div>
        <div className="mt-2 font-heading text-2xl font-bold">68% complete</div>
        <div className="mt-2 h-2 rounded-full bg-slate-100"><div className="h-2 w-[68%] rounded-full bg-[hsl(222_100%_56%)]" /></div>
        <div className="mt-3 flex items-center gap-2 text-xs text-slate-600"><CheckCircle2 className="h-4 w-4 text-emerald-600" /> Slab casting approved by client</div>
      </div>
    </div>
  );
}

export function About() {
  return (
    <section id="about" className="bg-background py-20 md:py-28">
      <div className="mx-auto grid max-w-7xl items-center gap-12 px-5 md:px-8 lg:grid-cols-2">
        <div className="grid grid-cols-2 gap-4">
          <img src={IMG.engineer} alt="Site engineer on site" className="h-72 w-full rounded-2xl object-cover" />
          <img src={IMG.tower} alt="Tower under construction" className="mt-10 h-72 w-full rounded-2xl object-cover" />
        </div>
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-accent">What is CIVIO</p>
          <h2 className="mt-3 font-heading text-3xl font-bold md:text-4xl">Built by project management consultants, for the people who build.</h2>
          <p className="mt-5 text-muted-foreground">
            CIVIO began as the digital backbone of a Project Management Consultancy. Today it powers construction companies of every size — replacing scattered WhatsApp photos, spreadsheets and paper registers with one transparent system of record.
          </p>
          <ul className="mt-6 space-y-3 text-sm">
            {["Weighted, evidence-backed progress — not guesswork", "Client approvals with a permanent decision history",
              "Defects tracked from discovery to verified closure", "Branded PDF reports delivered straight to inboxes"].map((t) => (
              <li key={t} className="flex gap-3"><CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-emerald-600" /> {t}</li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}

const FEATURES = [
  { icon: ClipboardCheck, t: "Progress & approvals", d: "Engineers submit dated photo evidence, PMs review, clients approve — every decision preserved." },
  { icon: ShieldAlert, t: "Quality & defects", d: "Severity-based defect register with escalation, assignment and verified closure." },
  { icon: IndianRupee, t: "Procurement & cost", d: "Material requests, purchase orders, invoices and budget vs. forecast in INR." },
  { icon: FileText, t: "Branded reports", d: "Progress, cost and completion PDFs with your logo, generated in seconds." },
  { icon: Users, t: "Teams & invites", d: "Invite engineers and clients by email — they land straight in your workspace." },
  { icon: Building2, t: "Multi-site control", d: "Portfolio dashboards, audit logs and role-based access for every project." },
];

export function Features() {
  return (
    <section id="features" className="bg-muted/40 py-20 md:py-28">
      <div className="mx-auto max-w-7xl px-5 md:px-8">
        <p className="text-xs font-semibold uppercase tracking-widest text-accent">The platform</p>
        <h2 className="mt-3 max-w-2xl font-heading text-3xl font-bold md:text-4xl">Everything a construction project needs, connected.</h2>
        <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f, i) => (
            <div key={f.t} className="group animate-fade-up rounded-2xl border bg-card p-6 transition-[transform,box-shadow] duration-300 hover:-translate-y-1 hover:shadow-lg" style={{ animationDelay: `${i * 60}ms` }} data-testid={`feature-${i}`}>
              <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary text-primary-foreground transition-colors group-hover:bg-[hsl(222_100%_56%)]"><f.icon className="h-5 w-5" /></div>
              <h3 className="mt-5 font-heading text-lg font-bold">{f.t}</h3>
              <p className="mt-2 text-sm text-muted-foreground">{f.d}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

export function Workspaces() {
  const items = [
    { icon: Home, img: IMG.villa, t: "Residential Construction", d: "Homes, villas and apartments. A simple homeowner view with a visual build timeline, one-tap approvals and site photos." },
    { icon: Building2, img: IMG.tower, t: "Commercial Construction", d: "Offices, retail and industrial. Full procurement, cost control, audit trails and multi-team coordination." },
  ];
  const roles = [[Briefcase, "Owners & PMs"], [HardHat, "Site engineers"], [UserRound, "Clients & homeowners"]];
  return (
    <section id="workspaces" className="bg-background py-20 md:py-28">
      <div className="mx-auto max-w-7xl px-5 md:px-8">
        <p className="text-xs font-semibold uppercase tracking-widest text-accent">Two tailored workspaces</p>
        <h2 className="mt-3 font-heading text-3xl font-bold md:text-4xl">Designed for how you build.</h2>
        <div className="mt-12 grid gap-6 md:grid-cols-2">
          {items.map((w) => (
            <div key={w.t} className="group relative overflow-hidden rounded-3xl" data-testid={`workspace-${w.icon === Home ? "residential" : "commercial"}`}>
              <img src={w.img} alt={w.t} className="h-80 w-full object-cover transition-transform duration-700 group-hover:scale-105" />
              <div className="absolute inset-0 bg-gradient-to-t from-[hsl(222_60%_11%)] via-[hsl(222_60%_11%)]/60 to-transparent" />
              <div className="absolute inset-x-0 bottom-0 p-7 text-white">
                <w.icon className="h-6 w-6 text-emerald-300" />
                <h3 className="mt-3 font-heading text-2xl font-bold">{w.t}</h3>
                <p className="mt-2 max-w-md text-sm text-white/75">{w.d}</p>
              </div>
            </div>
          ))}
        </div>
        <div className="mt-10 flex flex-wrap gap-3">
          {roles.map(([I, l]) => <span key={l} className="inline-flex items-center gap-2 rounded-full border bg-card px-4 py-2 text-sm font-medium"><I className="h-4 w-4 text-primary" /> {l}</span>)}
        </div>
      </div>
    </section>
  );
}

export function Contact() {
  return (
    <section id="contact" className="bg-[hsl(222_60%_11%)] py-20 text-white md:py-28">
      <div className="mx-auto grid max-w-7xl gap-12 px-5 md:px-8 lg:grid-cols-2">
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-emerald-300">Contact us</p>
          <h2 className="mt-3 font-heading text-3xl font-bold md:text-4xl">Let's build something great together.</h2>
          <p className="mt-4 max-w-md text-white/70">Questions about CIVIO, a demo for your team, or pricing for your company? Reach us directly — we usually reply within one business day.</p>
          <Link to="/register"><Button size="lg" className="mt-8 rounded-full bg-[hsl(222_100%_56%)] px-7 hover:bg-[hsl(222_100%_50%)]" data-testid="contact-register-btn">Register your company <ArrowRight className="h-4 w-4" /></Button></Link>
        </div>
        <div className="space-y-4">
          <a href={`mailto:${CONTACT.email}`} className="flex items-center gap-4 rounded-2xl border border-white/10 bg-white/5 p-5 transition-colors hover:bg-white/10" data-testid="contact-email">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-[hsl(222_100%_56%)]"><Mail className="h-5 w-5" /></div>
            <div><div className="text-xs uppercase tracking-widest text-white/50">Email</div><div className="font-heading text-lg font-semibold">{CONTACT.email}</div></div>
          </a>
          <a href={`tel:${CONTACT.tel}`} className="flex items-center gap-4 rounded-2xl border border-white/10 bg-white/5 p-5 transition-colors hover:bg-white/10" data-testid="contact-phone">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-emerald-500"><Phone className="h-5 w-5" /></div>
            <div><div className="text-xs uppercase tracking-widest text-white/50">Phone</div><div className="font-heading text-lg font-semibold">{CONTACT.phone}</div></div>
          </a>
          <div className="flex items-center gap-4 rounded-2xl border border-white/10 bg-white/5 p-5">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-white/10"><MapPin className="h-5 w-5" /></div>
            <div><div className="text-xs uppercase tracking-widest text-white/50">Serving</div><div className="font-heading text-lg font-semibold">Builders & PMCs across India</div></div>
          </div>
        </div>
      </div>
    </section>
  );
}

export function LandingFooter() {
  return (
    <footer className="border-t border-white/10 bg-[hsl(222_60%_8%)] py-8 text-sm text-white/50">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-5 md:px-8">
        <div className="flex items-center gap-2"><img src="/civio-icon.png" alt="" className="h-6 w-6 rounded bg-white p-0.5" /> © {new Date().getFullYear()} CIVIO. Your Build, Our Expertise.</div>
        <div className="flex gap-5"><a href={`mailto:${CONTACT.email}`} className="hover:text-white">{CONTACT.email}</a><a href={`tel:${CONTACT.tel}`} className="hover:text-white">{CONTACT.phone}</a></div>
      </div>
    </footer>
  );
}
