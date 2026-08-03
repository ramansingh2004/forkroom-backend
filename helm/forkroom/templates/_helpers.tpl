{{- define "forkroom.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "forkroom.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name (include "forkroom.name" .) | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{- define "forkroom.labels" -}}
app.kubernetes.io/name: {{ include "forkroom.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end }}

{{- define "forkroom.secretName" -}}
{{- if .Values.secrets.create }}{{ include "forkroom.fullname" . }}-secrets{{ else }}{{ required "secrets.existingSecret is required when secrets.create=false" .Values.secrets.existingSecret }}{{ end }}
{{- end }}
