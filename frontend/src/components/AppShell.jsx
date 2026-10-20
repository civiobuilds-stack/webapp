import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuLabel, DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { Badge } from "@/components/ui/badge";
import { LayoutDashboard, FolderKanban, Bell, LogOut, HardHat, Menu, X, Users, ShieldCheck, Settings, Warehouse, Receipt, Car, CalendarCheck, Lightbulb } from "lucide-react";
import { API, getToken } from "@/lib/api";
import { refreshPush } from "@/lib/push";
import { cn } from "@/lib/utils";
import { TrialEnded, SubscriptionBanner } from "@/components/TrialEnded";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, testid: "nav-dashboard" },
  { to: "/projects", label: "Projects", icon: FolderKanban, testid: "nav-projects" },
  { to: "/people", label: "People", icon: Users, testid: "nav-people", managerOnly: true },
  { to: "/store", label: "Company Store", icon: Warehouse, testid: "nav-store", commercialStaff: true },
  { to: "/accounts", label: "Billing", icon: Receipt, testid: "nav-accounts", roles: ["accounts", "admin"], module: "billing" },
  { to: "/fleet", label: "Company Vehicles", icon: Car, testid: "nav-fleet", roles: ["admin", "project_manager"], module: "vehicles" },
  { to: "/my-attendance", label: "My Attendance", icon: CalendarCheck, testid: "nav-my-attendance", attendance: true },
  { to: "/trips", label: "My Trips", icon: Car, testid: "nav-trips", roles: ["driver"], module: "vehicles" },
  { to: "/feature-request", label: "Request a feature", icon: Lightbulb, testid: "nav-feature-request", employee: true },
  { to: "/notifications", label: "Notifications", icon: Bell, testid: "nav-notifications" },
  { to: "/settings", label: "Company Settings", icon: Settings, testid: "nav-settings", adminOnly: true },
];

export function AppShell({ children }) {
  const { user, logout } = useAuth();
  const loc = useLocation();
  const navigate = useNavigate();
  const [unread, setUnread] = useState(0);
  const [mobileNav, setMobileNav] = useState(false);

  const loadUnread = () => api.get("/notifications").then((r) => setUnread(r.data.unread)).catch(() => {});
  useEffect(() => { loadUnread(); }, [loc.pathname]);
  useEffect(() => { refreshPush(); }, []);
  const [att, setAtt] = useState(null);
  useEffect(() => { if (user && user.role !== "client" && !user.subscription?.expired) api.get("/my-attendance/status").then((r) => setAtt(r.data)).catch(() => {}); }, [user, loc.pathname]);
  const expired = user?.subscription?.expired && user?.platform_role !== "super_admin";

  const manager = user?.role === "admin" || user?.role === "project_manager";
  const initials = (user?.name || "?").split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase();

  const nav = user?.platform_role === "super_admin"
    ? [{ to: "/superadmin", label: "Super Admin", icon: ShieldCheck, testid: "nav-superadmin" }, ...NAV]
    : NAV;

  const NavLinks = ({ onClick }) => (
    <nav className="flex flex-col gap-1">
      {user?.enterprise && (
        <div className="mb-3 flex items-center gap-2.5 rounded-xl border border-white/10 bg-white/5 px-3 py-2" data-testid="workspace-badge">
          {user.enterprise.has_logo && <img src={`${API}/enterprise/logo?auth=${getToken()}`} alt="" className="h-8 w-8 shrink-0 rounded-md bg-white object-contain p-0.5" data-testid="workspace-logo" />}
          <div className="min-w-0">
            <div className="truncate text-xs font-semibold text-white">{user.enterprise.display_name || user.enterprise.name}</div>
            <div className="text-[10px] uppercase tracking-widest text-white/50">{user.enterprise.business_type} workspace</div>
          </div>
        </div>
      )}
      {nav.filter((n) => (!n.managerOnly || manager) && (!n.adminOnly || user?.role === "admin")
        && (!n.roles || (n.roles.includes(user?.role) && (user?.enterprise?.modules || []).includes(n.module)))
        && (!n.attendance || att?.enabled || att?.can_review)
        && (!n.employee || (user?.role !== "client" && user?.platform_role !== "super_admin"))
        && (!n.commercialStaff || (user?.enterprise?.business_type === "commercial" && !["client", "driver"].includes(user?.role)))).map((n) => {
        const active = n.to === "/" ? loc.pathname === "/" : loc.pathname.startsWith(n.to);
        return (
          <Link key={n.to} to={n.to} onClick={onClick} data-testid={n.testid}
            className={cn("group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors",
              active ? "bg-primary text-primary-foreground" : "text-primary-foreground/70 hover:bg-white/10 hover:text-primary-foreground")}>
            <n.icon className="h-[18px] w-[18px]" />
            <span>{n.label}</span>
            {n.to === "/notifications" && unread > 0 && (
              <Badge className="ml-auto bg-rose-500 text-white" data-testid="nav-unread-count">{unread}</Badge>
            )}
          </Link>
        );
      })}
    </nav>
  );

  return (
    <div className="min-h-screen bg-background">
      {/* Sidebar (desktop) */}
      <aside className="fixed inset-y-0 left-0 hidden w-64 flex-col bg-[hsl(222_60%_11%)] p-4 lg:flex">
        <Brand />
        <div className="mt-8 flex-1"><NavLinks /></div>
        <UserCard user={user} initials={initials} logout={logout} />
      </aside>

      {/* Mobile nav drawer */}
      {mobileNav && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-black/50" onClick={() => setMobileNav(false)} />
          <div className="absolute inset-y-0 left-0 flex w-72 flex-col bg-[hsl(222_60%_11%)] p-4">
            <div className="flex items-center justify-between">
              <Brand />
              <button onClick={() => setMobileNav(false)} className="text-white"><X className="h-5 w-5" /></button>
            </div>
            <div className="mt-8 flex-1"><NavLinks onClick={() => setMobileNav(false)} /></div>
            <UserCard user={user} initials={initials} logout={logout} />
          </div>
        </div>
      )}

      {/* Top bar (mobile) */}
      <header className="sticky top-0 z-40 flex items-center justify-between border-b bg-card/90 px-4 py-3 backdrop-blur lg:hidden">
        <button onClick={() => setMobileNav(true)} data-testid="mobile-menu-btn" className="text-foreground"><Menu className="h-6 w-6" /></button>
        <div className="rounded-lg bg-white px-2 py-0.5"><img src="/civio-logo.png" alt="CIVIO" className="h-8" data-testid="mobile-brand-logo" /></div>
        <button onClick={() => navigate("/notifications")} className="relative" data-testid="mobile-bell-btn">
          <Bell className="h-6 w-6" />
          {unread > 0 && <span className="absolute -right-1 -top-1 h-4 w-4 rounded-full bg-rose-500 text-[10px] font-bold text-white">{unread}</span>}
        </button>
      </header>

      <main className="lg:pl-64">
        <div className="mx-auto max-w-[1500px] p-4 md:p-8">{expired ? <TrialEnded /> : <>
          <SubscriptionBanner sub={user?.subscription} />
          {att?.needs_check_in && !loc.pathname.startsWith("/my-attendance") && <div className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-sky-300 bg-sky-50 px-4 py-3 text-sm text-sky-900" data-testid="checkin-prompt">
            <span><CalendarCheck className="mr-1 inline h-4 w-4" /> You haven't checked in today.</span>
            <Button size="sm" onClick={() => navigate("/my-attendance")} data-testid="checkin-prompt-btn">Check in now</Button></div>}
          {children}</>}</div>
      </main>
    </div>
  );
}

function Brand() {
  return (
    <Link to="/" className="block rounded-xl bg-white px-3 py-1.5 transition-transform duration-200 hover:scale-[1.02]" data-testid="brand-logo">
      <img src="/civio-logo.png" alt="CIVIO — Your Build, Our Expertise" className="mx-auto h-14 object-contain" />
    </Link>
  );
}

function UserCard({ user, initials, logout }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button data-testid="user-menu-btn" className="flex w-full items-center gap-3 rounded-xl bg-white/5 p-2.5 text-left transition-colors hover:bg-white/10">
          <Avatar className="h-9 w-9"><AvatarFallback className="bg-[hsl(222_100%_56%)] text-sm text-white">{initials}</AvatarFallback></Avatar>
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-semibold text-white">{user?.name}</div>
            <div className="truncate text-[11px] text-white/50">{ROLE_LABEL[user?.role]}</div>
          </div>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel className="truncate">{user?.email}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={logout} data-testid="logout-btn" className="text-rose-600">
          <LogOut className="mr-2 h-4 w-4" /> Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
