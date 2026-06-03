"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardList,
  Loader2,
  RefreshCw,
  ShieldCheck,
  X,
} from "lucide-react";

import {
  listAuditEvents,
  verifyAuditChain,
} from "../lib/api";

const ACTION_LABEL = {
  suggestion_proposed: "Propuesta",
  suggestion_accepted: "Aceptada",
  suggestion_edited: "Editada",
  suggestion_rejected: "Rechazada",
  session_started: "Sesion iniciada",
  session_closed: "Sesion cerrada",
};

const ACTION_COLOR = {
  suggestion_proposed: "#64748b",
  suggestion_accepted: "#16a34a",
  suggestion_edited: "#0891b2",
  suggestion_rejected: "#dc2626",
  session_started: "#0ea5e9",
  session_closed: "#475569",
};

function formatTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("es-ES", {
    year: "2-digit",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function short(hash, n = 8) {
  if (!hash) return "—";
  return hash.slice(0, n) + "…";
}

export default function AuditPanel({ open, onClose, apiKey }) {
  const [events, setEvents] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [verifyResult, setVerifyResult] = useState(null);
  const [error, setError] = useState("");
  const [limit, setLimit] = useState(50);

  const loadEvents = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await listAuditEvents({ n: limit, apiKey });
      setEvents(data.entries || []);
      setTotal(data.total || 0);
    } catch (err) {
      setError(String(err.message || err));
      setEvents([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [limit, apiKey]);

  const runVerify = useCallback(async () => {
    setVerifying(true);
    setError("");
    setVerifyResult(null);
    try {
      const data = await verifyAuditChain({ apiKey });
      setVerifyResult(data);
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setVerifying(false);
    }
  }, [apiKey]);

  useEffect(() => {
    if (open) {
      loadEvents();
    }
  }, [open, loadEvents]);

  if (!open) return null;

  return (
    <div className="overlay" role="dialog" aria-modal="true">
      <aside className="assistantPanel" style={{ maxWidth: 980 }}>
        <header className="assistantHeader">
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <ShieldCheck size={22} />
            <div>
              <h2 style={{ margin: 0 }}>Audit log</h2>
              <p style={{ margin: 0, fontSize: 13, opacity: 0.7 }}>
                Trazabilidad clinica encadenada HMAC · solo metadata + hashes (sin PHI)
              </p>
            </div>
          </div>
          <button className="iconButton" aria-label="Cerrar" onClick={onClose}>
            <X size={22} />
          </button>
        </header>

        <div
          className="assistantToolbar"
          style={{
            display: "flex",
            gap: 8,
            flexWrap: "wrap",
            alignItems: "center",
            padding: "10px 24px",
            borderBottom: "1px solid var(--border, #e2e8f0)",
          }}
        >
          <button
            className="primaryButton subtle"
            onClick={loadEvents}
            disabled={loading}
            title="Recargar entradas"
          >
            {loading ? (
              <Loader2 size={16} className="spin" />
            ) : (
              <RefreshCw size={16} />
            )}
            <span>Recargar</span>
          </button>
          <button
            className="primaryButton"
            onClick={runVerify}
            disabled={verifying}
            title="Recalcula la cadena HMAC desde el inicio del archivo activo"
          >
            {verifying ? (
              <Loader2 size={16} className="spin" />
            ) : (
              <ShieldCheck size={16} />
            )}
            <span>Verificar cadena</span>
          </button>

          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13 }}>
            <span>Limite:</span>
            <select
              value={limit}
              onChange={(event) => setLimit(Number(event.target.value))}
              className="select"
              style={{ padding: "2px 6px" }}
            >
              {[20, 50, 100, 200, 500].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>

          <div style={{ marginLeft: "auto", fontSize: 12, opacity: 0.7 }}>
            Total registros: <strong>{total}</strong>
          </div>
        </div>

        {error && (
          <div
            style={{
              margin: "8px 24px",
              padding: "10px 12px",
              borderRadius: 6,
              background: "rgba(239,68,68,0.08)",
              color: "var(--danger, #b91c1c)",
              fontSize: 13,
              display: "flex",
              gap: 8,
              alignItems: "flex-start",
            }}
          >
            <AlertTriangle size={16} />
            <span>{error}</span>
          </div>
        )}

        {verifyResult && (
          <div
            style={{
              margin: "8px 24px",
              padding: "10px 12px",
              borderRadius: 6,
              background: verifyResult.ok
                ? "rgba(34,197,94,0.10)"
                : "rgba(239,68,68,0.10)",
              color: verifyResult.ok
                ? "var(--success, #166534)"
                : "var(--danger, #b91c1c)",
              fontSize: 13,
              display: "flex",
              gap: 8,
              alignItems: "flex-start",
            }}
          >
            {verifyResult.ok ? (
              <CheckCircle2 size={16} />
            ) : (
              <AlertTriangle size={16} />
            )}
            <div>
              <strong>
                {verifyResult.ok
                  ? `Cadena integra (${verifyResult.n_entries} entradas)`
                  : `Tampering detectado en entrada ${verifyResult.n_entries}`}
              </strong>
              {verifyResult.error && (
                <div style={{ marginTop: 4, opacity: 0.85 }}>{verifyResult.error}</div>
              )}
            </div>
          </div>
        )}

        <div style={{ padding: "0 24px 16px", overflow: "auto", flex: 1 }}>
          {events.length === 0 && !loading ? (
            <p
              style={{
                textAlign: "center",
                padding: "32px 16px",
                color: "var(--muted, #64748b)",
                fontSize: 13,
              }}
            >
              <ClipboardList size={32} style={{ opacity: 0.4 }} />
              <br />
              Sin entradas. ¿Audit log configurado?
              <br />
              Requiere <code>AUDIT_LOG_PATH</code> + <code>AUDIT_HMAC_KEY</code>.
            </p>
          ) : (
            <table
              style={{
                width: "100%",
                fontSize: 12,
                borderCollapse: "collapse",
              }}
            >
              <thead>
                <tr style={{ background: "var(--panel-2, #f1f5f9)", textAlign: "left" }}>
                  <th style={{ padding: "6px 8px" }}>#</th>
                  <th style={{ padding: "6px 8px" }}>Cuando</th>
                  <th style={{ padding: "6px 8px" }}>Accion</th>
                  <th style={{ padding: "6px 8px" }}>Usuario</th>
                  <th style={{ padding: "6px 8px" }}>Paciente</th>
                  <th style={{ padding: "6px 8px" }}>Pregunta</th>
                  <th style={{ padding: "6px 8px" }}>Codigos</th>
                  <th style={{ padding: "6px 8px" }} title="Hash SHA-256 de la evidencia">
                    Ev hash
                  </th>
                  <th style={{ padding: "6px 8px" }} title="Hash HMAC del eslabon">
                    Chain
                  </th>
                </tr>
              </thead>
              <tbody>
                {events.map((entry, idx) => {
                  const action = entry.action || "?";
                  return (
                    <tr
                      key={`${entry.chain_hmac}-${idx}`}
                      style={{
                        borderBottom: "1px solid var(--border, #e2e8f0)",
                      }}
                    >
                      <td style={{ padding: "6px 8px", color: "var(--muted, #64748b)" }}>
                        {idx + 1}
                      </td>
                      <td style={{ padding: "6px 8px", whiteSpace: "nowrap" }}>
                        {formatTime(entry.timestamp_utc)}
                      </td>
                      <td style={{ padding: "6px 8px" }}>
                        <span
                          style={{
                            display: "inline-block",
                            padding: "2px 6px",
                            borderRadius: 4,
                            background: `${ACTION_COLOR[action] || "#94a3b8"}22`,
                            color: ACTION_COLOR[action] || "#475569",
                            fontWeight: 600,
                          }}
                        >
                          {ACTION_LABEL[action] || action}
                        </span>
                      </td>
                      <td style={{ padding: "6px 8px" }}>{entry.user_id || "—"}</td>
                      <td style={{ padding: "6px 8px" }}>{entry.patient_id || "—"}</td>
                      <td style={{ padding: "6px 8px" }}>{entry.question_id || "—"}</td>
                      <td style={{ padding: "6px 8px" }}>
                        {(entry.selected_codes || []).join(", ") || "—"}
                      </td>
                      <td
                        style={{
                          padding: "6px 8px",
                          fontFamily: "monospace",
                          fontSize: 11,
                        }}
                        title={entry.evidence_hash || ""}
                      >
                        {short(entry.evidence_hash)}
                      </td>
                      <td
                        style={{
                          padding: "6px 8px",
                          fontFamily: "monospace",
                          fontSize: 11,
                        }}
                        title={entry.chain_hmac || ""}
                      >
                        {short(entry.chain_hmac)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        <footer
          style={{
            padding: "10px 24px",
            borderTop: "1px solid var(--border, #e2e8f0)",
            fontSize: 11,
            opacity: 0.7,
          }}
        >
          Audit log append-only encadenado HMAC-SHA256. Evidencia y texto libre
          se almacenan solo como hash. Para detalle del shape ver{" "}
          <code>docs/adr/0006-audit-log-hmac-chain.md</code>.
        </footer>
      </aside>
    </div>
  );
}
