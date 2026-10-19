import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";

export function ReasonDialog({ title, onClose, onConfirm, testid = "reason" }) {
  const [text, setText] = useState("");
  return (
    <Dialog open onOpenChange={onClose}><DialogContent className="sm:max-w-md">
      <DialogHeader><DialogTitle>{title}</DialogTitle></DialogHeader>
      <Textarea rows={3} placeholder="Reason (required)" value={text} onChange={(e) => setText(e.target.value)} data-testid={`${testid}-input`} />
      <DialogFooter><Button onClick={() => onConfirm(text.trim())} disabled={!text.trim()} data-testid={`${testid}-confirm`}>Confirm</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}
