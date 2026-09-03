{{- define "winbindex-api.name" -}}winbindex-api{{- end }}
{{- define "winbindex-api.fullname" -}}{{ .Release.Name }}-{{ include "winbindex-api.name" . }}{{- end }}
{{- define "winbindex-api.labels" -}}
app.kubernetes.io/name: {{ include "winbindex-api.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
{{- define "winbindex-api.selectorLabels" -}}
app.kubernetes.io/name: {{ include "winbindex-api.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
{{- define "winbindex-api.claimName" -}}
{{- if .Values.persistence.existingClaim }}{{ .Values.persistence.existingClaim }}{{ else }}{{ include "winbindex-api.fullname" . }}{{ end -}}
{{- end }}
