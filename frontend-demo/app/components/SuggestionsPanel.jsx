"use client";

import { useMemo, useState } from "react";
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import CheckIcon from "@mui/icons-material/Check";
import EditIcon from "@mui/icons-material/Edit";
import SubdirectoryArrowRightIcon from "@mui/icons-material/SubdirectoryArrowRight";

const RISK_LABELS = {
  low_confidence: "Baja confianza",
  free_text: "Texto libre",
  conflict: "Conflicto",
  uncertain_negation: "Negacion dudosa",
  no_audio_timestamp: "Sin timestamp",
  speaker_not_expected: "Hablante no esperado",
  online_provider_used: "Proveedor online",
  historical_temporality: "Temporalidad historica",
};

const SPEAKER_LABELS = {
  medico: "Medico",
  paciente: "Paciente",
  acompanante: "Acompanante",
  unknown: "Desconocido",
};

function hasBlockingRisk(s) {
  return s.technicalStatus !== "valid" || (s.riskFlags || []).length > 0;
}

// child questionId -> { id, text, triggerLabel } del padre que lo encadena.
function buildParentMap(questionsMap) {
  const parentOf = {};
  for (const q of Object.values(questionsMap || {})) {
    const transitions = q?.transitions || {};
    for (const [code, target] of Object.entries(transitions)) {
      if (!target || target === q.id) continue;
      if (!parentOf[target]) {
        parentOf[target] = {
          id: q.id,
          text: q.text,
          triggerLabel: q.codes?.[code] || code,
        };
      }
    }
  }
  return parentOf;
}

// Construye bosque: nodo hijo si su pregunta-padre tambien esta sugerida.
function buildForest(items, parentOf) {
  const byQid = new Map();
  for (const s of items) if (!byQid.has(s.questionId)) byQid.set(s.questionId, s);

  const childrenOf = new Map();
  const roots = [];
  for (const s of items) {
    const parent = parentOf[s.questionId];
    if (parent && byQid.has(parent.id) && parent.id !== s.questionId) {
      if (!childrenOf.has(parent.id)) childrenOf.set(parent.id, []);
      childrenOf.get(parent.id).push(s);
    } else {
      roots.push(s);
    }
  }
  return { childrenOf, roots, byQid };
}

export default function SuggestionsPanel({
  groups,
  questionsMap,
  acceptedIds,
  onAccept,
}) {
  const parentOf = useMemo(() => buildParentMap(questionsMap), [questionsMap]);

  const items = useMemo(
    () => (groups || []).flatMap((g) => g.items),
    [groups],
  );
  const { childrenOf, roots } = useMemo(
    () => buildForest(items, parentOf),
    [items, parentOf],
  );

  // Agrupa raices por seccion preservando orden.
  const sections = useMemo(() => {
    const map = new Map();
    for (const s of roots) {
      const key = s.backendSection || s.sectionId || "Otras";
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(s);
    }
    return Array.from(map, ([segment, rootItems]) => ({ segment, rootItems }));
  }, [roots]);

  const acceptedSet = useMemo(() => new Set(acceptedIds || []), [acceptedIds]);
  const visited = new Set();

  function renderNode(s, depth) {
    if (visited.has(s.id)) return null;
    visited.add(s.id);
    const kids = childrenOf.get(s.questionId) || [];
    const parent = parentOf[s.questionId];
    const isChild = depth > 0;

    return (
      <Box key={s.id} sx={{ position: "relative" }}>
        <Box
          sx={
            isChild
              ? {
                  pl: 2,
                  ml: 1.5,
                  borderLeft: "2px solid",
                  borderColor: "divider",
                }
              : {}
          }
        >
          {isChild && parent && (
            <Stack
              direction="row"
              alignItems="center"
              spacing={0.5}
              sx={{ mt: 1, color: "text.secondary" }}
            >
              <SubdirectoryArrowRightIcon sx={{ fontSize: 15 }} />
              <Typography variant="caption" sx={{ fontWeight: 600 }}>
                depende de: {parent.text}
                {parent.triggerLabel ? ` → ${parent.triggerLabel}` : ""}
              </Typography>
            </Stack>
          )}
          <SuggestionCard
            suggestion={s}
            question={questionsMap[s.questionId]}
            accepted={acceptedSet.has(s.id)}
            sequential={isChild || kids.length > 0}
            onAccept={onAccept}
          />
          {kids.map((k) => renderNode(k, depth + 1))}
        </Box>
      </Box>
    );
  }

  if (!sections.length) {
    return (
      <Typography variant="body2" sx={{ color: "text.secondary", py: 2 }}>
        Las respuestas propuestas apareceran tras procesar
      </Typography>
    );
  }

  return (
    <Stack spacing={2.5}>
      {sections.map(({ segment, rootItems }) => (
        <Box key={segment}>
          <Stack
            direction="row"
            alignItems="center"
            spacing={1}
            sx={{ mb: 1 }}
          >
            <Typography
              variant="subtitle2"
              sx={{
                fontWeight: 800,
                color: "primary.main",
                letterSpacing: 0.3,
              }}
            >
              {segment}
            </Typography>
            <Chip
              label={rootItems.length}
              size="small"
              sx={{
                height: 20,
                fontWeight: 800,
                bgcolor: "primary.main",
                color: "#fff",
              }}
            />
          </Stack>
          <Stack spacing={1.5}>
            {rootItems.map((s) => renderNode(s, 0))}
          </Stack>
        </Box>
      ))}
    </Stack>
  );
}

function SuggestionCard({ suggestion, question, accepted, sequential, onAccept }) {
  const [editing, setEditing] = useState(false);
  const [selectedCodes, setSelectedCodes] = useState(
    suggestion.selectedCodes || [],
  );
  const [freeText, setFreeText] = useState(suggestion.freeText || "");

  const codes = question?.codes || {};
  const type = question?.question_type || "yesno";
  const freeTextCode = useMemo(
    () =>
      Object.entries(codes).find(([, label]) => /#TEXTO_LIBRE#/i.test(label))?.[0],
    [codes],
  );
  const editableCodes = useMemo(
    () => Object.entries(codes).filter(([code]) => code !== freeTextCode),
    [codes, freeTextCode],
  );

  const confidencePct = Math.round((suggestion.confidence || 0) * 100);
  const highConf = (suggestion.confidence || 0) >= 0.7;
  const isConflict = suggestion.status === "conflict";
  const blocking = hasBlockingRisk(suggestion);

  function commitEdit() {
    const labels = selectedCodes
      .map((c) => codes[c])
      .filter((label) => label && !/#TEXTO_LIBRE#/i.test(label));
    const answer =
      labels.length > 0 ? labels.join(", ") : freeText || "(sin valor)";
    onAccept({
      ...suggestion,
      selectedCodes,
      freeText: freeText || null,
      answer,
      edited: true,
    });
    setEditing(false);
  }

  function toggleMultiple(code) {
    setSelectedCodes((prev) =>
      prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code],
    );
  }

  const isSingle = type === "yesno" || type === "yesnoremember" || type === "choice";

  return (
    <Card
      variant="outlined"
      sx={{
        mt: 1,
        borderColor: isConflict ? "warning.main" : "divider",
        borderLeft: sequential ? "3px solid" : "1px solid",
        borderLeftColor: sequential ? "primary.main" : "divider",
        borderRadius: 2,
      }}
    >
      <CardContent sx={{ p: 1.75, "&:last-child": { pb: 1.75 } }}>
        <Stack
          direction="row"
          justifyContent="space-between"
          alignItems="flex-start"
          spacing={1}
        >
          <Box sx={{ minWidth: 0 }}>
            <Typography
              variant="caption"
              sx={{
                color: "text.secondary",
                fontFamily: "monospace",
                fontWeight: 700,
              }}
            >
              {suggestion.questionId}
            </Typography>
            <Typography
              variant="subtitle2"
              sx={{ fontWeight: 800, color: "text.primary", lineHeight: 1.3 }}
            >
              {suggestion.question}
            </Typography>
          </Box>
          <Tooltip title="Confianza de la IA">
            <Chip
              label={`${confidencePct}%`}
              size="small"
              color={highConf ? "success" : "default"}
              sx={{ fontWeight: 800 }}
            />
          </Tooltip>
        </Stack>

        {(suggestion.riskFlags?.length > 0 ||
          suggestion.previous ||
          (suggestion.audioStart !== null && suggestion.audioEnd !== null) ||
          suggestion.speaker) && (
          <Stack
            direction="row"
            flexWrap="wrap"
            gap={0.5}
            sx={{ mt: 0.75 }}
          >
            {suggestion.previous && (
              <Chip
                label={`Actual: ${suggestion.previous}`}
                size="small"
                variant="outlined"
                color="warning"
                sx={{ height: 22 }}
              />
            )}
            {(suggestion.riskFlags || []).map((flag) => (
              <Chip
                key={flag}
                label={RISK_LABELS[flag] || flag}
                size="small"
                variant="outlined"
                color="error"
                sx={{ height: 22 }}
              />
            ))}
            {suggestion.audioStart !== null &&
              suggestion.audioEnd !== null && (
                <Chip
                  label={`Audio ${Number(suggestion.audioStart).toFixed(1)}-${Number(
                    suggestion.audioEnd,
                  ).toFixed(1)}s`}
                  size="small"
                  variant="outlined"
                  sx={{ height: 22 }}
                />
              )}
            {suggestion.speaker && (
              <Chip
                label={SPEAKER_LABELS[suggestion.speaker] || suggestion.speaker}
                size="small"
                variant="outlined"
                sx={{ height: 22 }}
              />
            )}
          </Stack>
        )}

        {suggestion.technicalStatus &&
          suggestion.technicalStatus !== "valid" &&
          suggestion.reason && (
            <Typography
              variant="caption"
              sx={{ display: "block", mt: 0.5, color: "error.main" }}
            >
              {suggestion.reason}
            </Typography>
          )}

        {/* Respuesta / edicion */}
        {!editing ? (
          <Box
            sx={{
              mt: 1,
              p: 1,
              borderRadius: 1.5,
              bgcolor: (t) => `${t.palette.primary.main}0d`,
              border: "1px solid",
              borderColor: (t) => `${t.palette.primary.main}22`,
            }}
          >
            <Typography variant="body2" sx={{ fontWeight: 700 }}>
              {suggestion.answer}
            </Typography>
          </Box>
        ) : isSingle ? (
          <Box
            sx={{
              mt: 1,
              display: "grid",
              gridTemplateColumns:
                editableCodes.length <= 2 ? "1fr 1fr" : "1fr 1fr 1fr",
              gap: 0.75,
            }}
          >
            {editableCodes.map(([code, label]) => {
              const sel = selectedCodes[0] === code;
              return (
                <Button
                  key={code}
                  variant={sel ? "contained" : "outlined"}
                  size="small"
                  onClick={() => setSelectedCodes([code])}
                  sx={{ minHeight: 44, lineHeight: 1.2, fontSize: "0.78rem" }}
                >
                  {label}
                </Button>
              );
            })}
            {freeTextCode && (
              <TextField
                size="small"
                placeholder="Texto libre"
                value={freeText}
                onChange={(e) => {
                  setFreeText(e.target.value);
                  if (e.target.value) setSelectedCodes([freeTextCode]);
                }}
                sx={{ gridColumn: "1 / -1" }}
              />
            )}
          </Box>
        ) : type === "multiple" ? (
          <Box
            sx={{
              mt: 1,
              display: "flex",
              flexWrap: "wrap",
              gap: 0.75,
            }}
          >
            {editableCodes.map(([code, label]) => {
              const sel = selectedCodes.includes(code);
              return (
                <Chip
                  key={code}
                  label={label}
                  clickable
                  color={sel ? "primary" : "default"}
                  variant={sel ? "filled" : "outlined"}
                  onClick={() => toggleMultiple(code)}
                />
              );
            })}
            {freeTextCode && (
              <TextField
                size="small"
                placeholder="Texto libre"
                value={freeText}
                onChange={(e) => setFreeText(e.target.value)}
                sx={{ width: "100%", mt: 0.5 }}
              />
            )}
          </Box>
        ) : (
          <TextField
            multiline
            minRows={2}
            fullWidth
            size="small"
            sx={{ mt: 1 }}
            value={freeText}
            onChange={(e) => setFreeText(e.target.value)}
            placeholder="Respuesta libre"
          />
        )}

        {suggestion.evidence && (
          <Box
            sx={{
              mt: 1,
              pl: 1.25,
              borderLeft: "3px solid",
              borderColor: "divider",
              color: "text.secondary",
            }}
          >
            <Typography variant="caption" sx={{ fontStyle: "italic" }}>
              {suggestion.evidence}
            </Typography>
          </Box>
        )}

        <Stack direction="row" spacing={1} sx={{ mt: 1.25 }} flexWrap="wrap">
          {!accepted && !editing && !blocking && (
            <Button
              size="small"
              variant="contained"
              color="success"
              startIcon={<CheckIcon />}
              onClick={() => onAccept(suggestion)}
            >
              Aceptar
            </Button>
          )}
          {!accepted && !editing && blocking && (
            <Button size="small" variant="outlined" disabled>
              Requiere revision
            </Button>
          )}
          {!accepted && !editing && (
            <Button
              size="small"
              variant="text"
              startIcon={<EditIcon />}
              onClick={() => setEditing(true)}
            >
              Editar
            </Button>
          )}
          {!accepted && editing && (
            <Button
              size="small"
              variant="contained"
              color="success"
              startIcon={<CheckIcon />}
              onClick={commitEdit}
            >
              Guardar
            </Button>
          )}
          {!accepted && editing && (
            <Button
              size="small"
              variant="text"
              onClick={() => {
                setSelectedCodes(suggestion.selectedCodes || []);
                setFreeText(suggestion.freeText || "");
                setEditing(false);
              }}
            >
              Cancelar
            </Button>
          )}
          {accepted && (
            <Button
              size="small"
              variant="outlined"
              color="success"
              startIcon={<CheckIcon />}
              disabled
            >
              Aplicada
            </Button>
          )}
        </Stack>
      </CardContent>
    </Card>
  );
}
