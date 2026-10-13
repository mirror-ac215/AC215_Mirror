import { Link, useNavigate } from "@tanstack/react-router";
import { ChevronDown, LogOut, Repeat } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import * as api from "@/lib/api/client";
import { setRole, useRole } from "@/lib/role";

export function TopNav() {
  const role = useRole();
  const navigate = useNavigate();

  const initials = role === "patient" ? "AO" : "DR";
  const name = role === "patient" ? "Amara Okafor" : "Dr. Elena Voss";
  const subtitle = role === "patient" ? "Patient" : "Clinician";

  return (
    <header className="sticky top-0 z-40 border-b border-border/70 bg-card/80 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5">
        <Link
          to={role === "patient" ? "/session" : "/clinician"}
          className="flex items-center gap-2.5"
        >
          <span className="brand-gradient h-7 w-7 rounded-[9px]" />
          <span className="font-serif text-xl tracking-tight text-ink">Mirror</span>
        </Link>

        <DropdownMenu>
          <DropdownMenuTrigger className="flex items-center gap-2 rounded-full border border-border bg-card py-1 pl-1 pr-2.5 outline-none hover:bg-secondary focus-visible:ring-2 focus-visible:ring-ring/40">
            <span className="brand-gradient flex h-8 w-8 items-center justify-center rounded-full text-xs font-semibold text-white">
              {initials}
            </span>
            <span className="hidden text-sm text-body sm:inline">{name}</span>
            <ChevronDown className="h-4 w-4 text-muted-ink" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-60 rounded-xl">
            <DropdownMenuLabel className="font-normal">
              <p className="text-sm text-ink">{name}</p>
              <p className="text-xs text-muted-ink">{subtitle}</p>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              className="text-xs text-muted-ink"
              onSelect={() => {
                const next = role === "patient" ? "clinician" : "patient";
                setRole(next);
                navigate({ to: next === "patient" ? "/consent" : "/clinician" });
              }}
            >
              <Repeat className="h-3.5 w-3.5" />
              Switch role (demo)
            </DropdownMenuItem>
            <DropdownMenuItem
              className="text-sm"
              onSelect={() => {
                api.logout();
                setRole("patient");
                navigate({ to: "/" });
              }}
            >
              <LogOut className="h-4 w-4" />
              Log out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
