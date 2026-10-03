"use client";

import { Check, Plus, Route, Trash2 } from "lucide-react";
import Link from "next/link";
import { useCallback, useState } from "react";
import { useToken } from "@/lib/auth";
import { listAdminAgencies, listAdminRoutingRules } from "@/lib/endpoints";
import { eventTypeDescription } from "@/lib/status";
import {
  EVENT_TYPES,
  type AgencyResponse,
  type EventType,
  type RoutingRule,
} from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/ui/card";
import { EmptyState, ErrorState } from "@/components/ui/empty-state";
import { SkeletonRows } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeadCell,
  TableRow,
} from "@/components/ui/table";
import { AddRoutingRuleDialog, RemoveRoutingRuleDialog } from "./routing-dialogs";

/**
 * The City Admin's routing matrix.
 *
 * Rows are the backend's four event types (shown even when empty, exactly as
 * `GET /routing/matrix` defaults them in); columns are the city's agencies. A
 * checkmark means the (event type, agency) rule exists — activate it to open
 * the removal dialog — and a plus means it does not — activate it to create it.
 *
 * Data comes from `GET /admin/routing`, not the matrix endpoint: the matrix
 * returns agency names only, which cannot identify which rule to delete or
 * whether a pair is already assigned. The rule list carries `agency_id`, so
 * the same grid is reconstructed here without a second request.
 *
 * Nothing is optimistic. Rows change only after the API confirms, so a 409
 * duplicate or a 404 on removal leaves the grid exactly as it was and says
 * why.
 */
export function AdminRoutingMatrix() {
  const token = useToken();

  const rulesState = useApi<RoutingRule[]>(
    useCallback((signal) => listAdminRoutingRules({ token, signal }), [token]),
    [token],
  );
  const agenciesState = useApi<AgencyResponse[]>(
    useCallback(
      (signal) => listAdminAgencies({ limit: 100 }, { token, signal }),
      [token],
    ),
    [token],
  );

  const [adding, setAdding] = useState<{
    event_type?: EventType;
    agency?: { id: string; name: string };
  } | null>(null);
  const [removing, setRemoving] = useState<RoutingRule | null>(null);

  const rules = rulesState.data;
  const agencies = agenciesState.data;

  if (rulesState.error) {
    return (
      <Panel bodyClassName="p-0">
        <ErrorState error={rulesState.error} onRetry={rulesState.reload} />
      </Panel>
    );
  }

  if (agenciesState.error) {
    return (
      <Panel bodyClassName="p-0">
        <ErrorState error={agenciesState.error} onRetry={agenciesState.reload} />
      </Panel>
    );
  }

  if (rulesState.isLoading || agenciesState.isLoading || !rules || !agencies) {
    return (
      <Panel bodyClassName="p-0">
        <div className="border-b border-line p-4">
          <p className="text-[13px] text-ink-500">Loading routing rules…</p>
        </div>
        <SkeletonRows rows={EVENT_TYPES.length} columns={5} />
      </Panel>
    );
  }

  // Columns are the agencies list, plus any agency a rule references that the
  // capped agencies page did not include — a configured rule is never hidden
  // just because its column would otherwise be missing.
  const agencyColumns: { id: string; name: string }[] = agencies.map(
    (agency) => ({ id: agency.id, name: agency.name }),
  );
  for (const rule of rules) {
    if (!agencyColumns.some((column) => column.id === rule.agency_id)) {
      agencyColumns.push({ id: rule.agency_id, name: rule.agency_name });
    }
  }

  if (agencyColumns.length === 0) {
    return (
      <Panel bodyClassName="p-0">
        <EmptyState
          icon={Route}
          title="No agencies in this city yet"
          description="Routing rules assign agencies to event types. Create the department first, then come back to build the matrix."
          action={
            <Button asChild variant="primary">
              <Link href="/admin/agencies">Go to Agencies</Link>
            </Button>
          }
        />
      </Panel>
    );
  }

  const assignedKey = (eventType: EventType, agencyId: string) =>
    `${eventType} ${agencyId}`;
  const assigned = new Set(
    rules.map((rule) => assignedKey(rule.event_type, rule.agency_id)),
  );
  const ruleFor = (eventType: EventType, agencyId: string) =>
    rules.find(
      (rule) => rule.event_type === eventType && rule.agency_id === agencyId,
    );

  return (
    <div className="space-y-5">
      <Panel bodyClassName="p-0">
        {/* Toolbar: the count is a total — this endpoint is not paginated. */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line p-4">
          <p className="text-[13px] text-ink-500">
            <span className="tabular font-medium text-ink-800">{rules.length}</span>{" "}
            routing {rules.length === 1 ? "rule" : "rules"} configured
            {rulesState.isRefreshing && " · refreshing…"}
          </p>
          <Button variant="primary" icon={<Plus />} onClick={() => setAdding({})}>
            Add routing rule
          </Button>
        </div>

        {/* Legend for the cells below. Hidden on narrow screens, where the
            cards carry labelled buttons instead. */}
        <div className="hidden flex-wrap items-center gap-x-5 gap-y-1.5 border-b border-line px-4 py-2.5 text-[12px] text-ink-500 md:flex">
          <span className="flex items-center gap-1.5">
            <span className="inline-flex size-5 items-center justify-center rounded-full bg-positive-soft text-positive-ink">
              <Check aria-hidden className="size-3" />
            </span>
            Assigned — activate to remove
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-flex size-5 items-center justify-center rounded-full border border-dashed border-ink-300 text-ink-400">
              <Plus aria-hidden className="size-3" />
            </span>
            Not assigned — activate to add
          </span>
        </div>

        {/* Matrix from `md` up. */}
        <div className="hidden overflow-x-auto md:block">
          <Table>
            <caption className="sr-only">
              Agencies assigned to review each event type
            </caption>
            <TableHead>
              <TableRow className="hover:bg-transparent">
                <TableHeadCell>Event type</TableHeadCell>
                {agencyColumns.map((agency) => (
                  <TableHeadCell key={agency.id} className="text-center">
                    {agency.name}
                  </TableHeadCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {EVENT_TYPES.map((eventType) => (
                <TableRow key={eventType}>
                  <TableCell>
                    <span className="block text-[13px] font-medium text-ink-900">
                      {eventType}
                    </span>
                    <span className="mt-0.5 block text-[12px] text-ink-400">
                      {eventTypeDescription(eventType)}
                    </span>
                  </TableCell>
                  {agencyColumns.map((agency) => {
                    const isAssigned = assigned.has(
                      assignedKey(eventType, agency.id),
                    );

                    if (isAssigned) {
                      const rule = ruleFor(eventType, agency.id);
                      return (
                        <TableCell key={agency.id} className="text-center">
                          <button
                            type="button"
                            title={`Remove ${agency.name} from ${eventType}`}
                            aria-label={`Remove ${agency.name} from ${eventType} reviews`}
                            className="inline-flex size-7 items-center justify-center rounded-full bg-positive-soft text-positive-ink ring-1 ring-inset ring-positive/20 transition-colors hover:bg-positive hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
                            onClick={() => rule && setRemoving(rule)}
                          >
                            <Check aria-hidden className="size-4" />
                          </button>
                        </TableCell>
                      );
                    }

                    return (
                      <TableCell key={agency.id} className="text-center">
                        <button
                          type="button"
                          title={`Assign ${agency.name} to ${eventType}`}
                          aria-label={`Assign ${agency.name} to ${eventType} reviews`}
                          className="inline-flex size-7 items-center justify-center rounded-full border border-dashed border-ink-300 text-ink-400 transition-colors hover:border-brand-400 hover:bg-brand-50 hover:text-brand-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
                          onClick={() =>
                            setAdding({
                              event_type: eventType,
                              agency: { id: agency.id, name: agency.name },
                            })
                          }
                        >
                          <Plus aria-hidden className="size-4" />
                        </button>
                      </TableCell>
                    );
                  })}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>

        {/* Cards below `md`. The same rules, with labelled actions instead of
            the matrix cells' icon-only affordance. */}
        <ul className="divide-y divide-line md:hidden">
          {EVENT_TYPES.map((eventType) => {
            const assignedToType = rules.filter(
              (rule) => rule.event_type === eventType,
            );

            return (
              <li key={eventType} className="px-4 py-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-ink-900">{eventType}</p>
                    <p className="mt-0.5 text-[12px] text-ink-400">
                      {eventTypeDescription(eventType)}
                    </p>
                  </div>
                  <Button
                    variant="default"
                    size="sm"
                    icon={<Plus aria-hidden />}
                    aria-label={`Add an agency to ${eventType}`}
                    onClick={() => setAdding({ event_type: eventType })}
                  >
                    Add
                  </Button>
                </div>

                {assignedToType.length === 0 ? (
                  <p className="mt-2.5 rounded-control border border-attention/20 bg-attention-soft px-3 py-2 text-[12px] leading-relaxed text-attention-ink">
                    Not assigned — {eventType} applications are rejected at
                    submission until an agency is added.
                  </p>
                ) : (
                  <ul className="mt-2.5 flex flex-wrap gap-1.5">
                    {assignedToType.map((rule) => (
                      <li key={rule.agency_id}>
                        <Button
                          variant="subtle"
                          size="sm"
                          icon={<Trash2 aria-hidden />}
                          className="text-ink-600 hover:bg-critical-soft hover:text-critical-ink"
                          aria-label={`Remove ${rule.agency_name} from ${eventType}`}
                          onClick={() => setRemoving(rule)}
                        >
                          {rule.agency_name}
                        </Button>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      </Panel>

      {/* How routing actually behaves — every sentence here is enforced in
          `app/core/routing.py` or the submit path, not aspirational. */}
      <div className="space-y-3 px-1">
        <p className="text-[13px] leading-relaxed text-ink-400">
          Each row is the complete base set for that event type: the server
          hard-codes no agencies of its own, so whatever this matrix holds is
          what applies. An event type left with no agencies blocks submission of
          that type until a rule is added again.
        </p>
        <p className="text-[13px] leading-relaxed text-ink-400">
          <span className="font-medium text-ink-600">
            Fire is added automatically
          </span>{" "}
          when an application&rsquo;s expected attendance is over 5,000 —
          strictly greater than, so exactly 5,000 does not count. That override
          applies on top of this matrix for every event type and cannot be
          switched off from this screen; if Fire is already assigned here, large
          events still get a single Fire review rather than two. Removing a rule
          never touches review tasks that already exist — new submissions follow
          the updated matrix.
        </p>
      </div>

      {adding && (
        <AddRoutingRuleDialog
          initial={adding}
          rules={rules}
          onClose={() => setAdding(null)}
          onDone={rulesState.reload}
        />
      )}

      {removing && (
        <RemoveRoutingRuleDialog
          rule={removing}
          rules={rules}
          onClose={() => setRemoving(null)}
          onDone={rulesState.reload}
        />
      )}
    </div>
  );
}
