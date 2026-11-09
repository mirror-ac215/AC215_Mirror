import { Link, useNavigate } from "@tanstack/react-router";
import { ChevronDown, LogOut } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import * as api from "@/lib/api/client";
import { USE_MOCK_API } from "@/lib/config";
import { useAuthenticatedUser } from "@/lib/role";

export function TopNav() {
  const user = useAuthenticatedUser();
  const role = user?.role ?? "patient";
  const navigate = useNavigate();

  // Demo names only in mock mode. A real login gives us a role, not a person's name.
  const demo =
    role === "patient"
      ? { initials: "AO", name: "Amara Okafor" }
      : { initials: "DR", name: "Dr. Elena Voss" };
  const real = { initials: role === "patient" ? "P" : "C", name: "Signed in" };
  const { initials, name } = USE_MOCK_API ? demo : real;
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
            <DropdownMenuItem
              className="text-sm"
              onSelect={() => {
                api.logout();
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
