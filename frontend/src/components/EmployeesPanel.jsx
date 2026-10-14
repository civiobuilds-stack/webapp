import { useEffect, useState } from "react";
import { api, apiError } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/format";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Pencil, Settings2 } from "lucide-react";
import { toast } from "sonner";

function Pick({ value, onChange, items, testid, placeholder }) {
  return (
    <Select value={value || ""} onValueChange={onChange}><SelectTrigger data-testid={testid}><SelectValue placeholder={placeholder} /></SelectTrigger>
      <SelectContent>{items.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}</SelectContent></Select>
  );
}

function EmployeeDialog({ emp, org, all, onClose, onDone }) {
  const [f, setF] = useState({ employee_id: emp.employee_id || "", designation: emp.designation || "", department: emp.department || "",
    reporting_manager_id: emp.reporting_manager_id || "", name: emp.name, phone: emp.phone || "" });
  const save = async () => {
    try { await api.put(`/employees/${emp.id}`, { ...f, reporting_manager_id: f.reporting_manager_id || null }); toast.success("Employee updated"); onDone(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md"><DialogHeader><DialogTitle>Employee record — {emp.name}</DialogTitle></DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5"><Label>Employee ID</Label><Input value={f.employee_id} onChange={(e) => setF({ ...f, employee_id: e.target.value })} data-testid="emp-id-input" /></div>
          <div className="space-y-1.5"><Label>Name</Label><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} data-testid="emp-name-input" /></div>
          <div className="space-y-1.5"><Label>Designation</Label><Pick value={f.designation} onChange={(v) => setF({ ...f, designation: v })} items={org.designations.map((d) => [d, d])} testid="emp-designation-select" placeholder="Select" /></div>
          <div className="space-y-1.5"><Label>Department</Label><Pick value={f.department} onChange={(v) => setF({ ...f, department: v })} items={org.departments.map((d) => [d, d])} testid="emp-department-select" placeholder="Select" /></div>
          <div className="space-y-1.5 sm:col-span-2"><Label>Reporting manager</Label>
            <Pick value={f.reporting_manager_id} onChange={(v) => setF({ ...f, reporting_manager_id: v })} items={all.filter((u) => u.id !== emp.id).map((u) => [u.id, u.name])} testid="emp-manager-select" placeholder="None" /></div>
        </div>
        <DialogFooter><Button onClick={save} disabled={!f.employee_id || !f.designation || !f.department} data-testid="emp-save-btn">Save</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function OrgDialog({ org, onClose, onDone }) {
  const [d, setD] = useState(org.departments.join("\n"));
  const [g, setG] = useState(org.designations.join("\n"));
  const save = async () => {
    try { await api.put("/org/config", { departments: d.split("\n"), designations: g.split("\n") }); toast.success("Organisation updated"); onDone(); }
    catch (e) { toast.error(apiError(e.response?.data?.detail)); }
  };
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md"><DialogHeader><DialogTitle>Departments & designations</DialogTitle></DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5"><Label>Departments (one per line)</Label><Textarea rows={8} value={d} onChange={(e) => setD(e.target.value)} data-testid="org-departments-input" /></div>
          <div className="space-y-1.5"><Label>Designations (one per line)</Label><Textarea rows={8} value={g} onChange={(e) => setG(e.target.value)} data-testid="org-designations-input" /></div>
        </div>
        <DialogFooter><Button onClick={save} data-testid="org-save-btn">Save</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function EmployeesPanel({ isAdmin, refreshKey }) {
  const [emps, setEmps] = useState([]);
  const [org, setOrg] = useState(null);
  const [dlg, setDlg] = useState(null);
  const load = () => { api.get("/employees").then((r) => setEmps(r.data)).catch(() => {}); api.get("/org/config").then((r) => setOrg(r.data)).catch(() => {}); };
  useEffect(() => { load(); }, [refreshKey]);
  if (!org) return null;
  const name = (id) => emps.find((e) => e.id === id)?.name;
  return (
    <div data-testid="employees-panel">
      <div className="mb-3 flex items-center justify-between"><h2 className="font-heading text-lg font-semibold">Employee directory</h2>
        {isAdmin && <Button size="sm" variant="outline" onClick={() => setDlg("org")} data-testid="org-config-btn"><Settings2 className="h-4 w-4" /> Departments & designations</Button>}</div>
      <Card className="divide-y">
        {emps.map((e) => (
          <div key={e.id} className="flex flex-wrap items-center justify-between gap-2 p-3 text-sm" data-testid="employee-row">
            <div><b>{e.name}</b> <span className="text-xs text-muted-foreground">· {e.employee_id || "No ID"} · {ROLE_LABEL[e.role]}</span>
              <div className="text-xs text-muted-foreground">{[e.designation, e.department, e.reporting_manager_id && `reports to ${name(e.reporting_manager_id)}`, `${e.project_count} project(s)`].filter(Boolean).join(" · ")}</div></div>
            {isAdmin && <Button size="sm" variant="ghost" onClick={() => setDlg(e)} data-testid="edit-employee-btn"><Pencil className="h-4 w-4" /></Button>}
          </div>
        ))}
      </Card>
      {dlg === "org" && <OrgDialog org={org} onClose={() => setDlg(null)} onDone={() => { setDlg(null); load(); }} />}
      {dlg && dlg !== "org" && <EmployeeDialog emp={dlg} org={org} all={emps} onClose={() => setDlg(null)} onDone={() => { setDlg(null); load(); }} />}
    </div>
  );
}
