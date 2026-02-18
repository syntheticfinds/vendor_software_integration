import apiClient from './client';

export interface SignalEvent {
  id: string;
  company_id: string;
  software_id: string;
  source_type: string;
  source_id: string | null;
  event_type: string;
  severity: string | null;
  title: string | null;
  body: string | null;
  event_metadata: Record<string, unknown> | null;
  occurred_at: string;
  created_at: string;
}

export interface SignalEventList {
  items: SignalEvent[];
  total: number;
}

export interface HealthScore {
  id: string;
  company_id: string;
  software_id: string;
  score: number;
  category_breakdown: Record<string, number>;
  signal_summary: string | null;
  signal_count: number;
  confidence_tier: string;
  scoring_window_start: string;
  scoring_window_end: string;
  created_at: string;
}

export interface ReviewDraft {
  id: string;
  company_id: string;
  software_id: string;
  health_score_id: string | null;
  draft_subject: string | null;
  draft_body: string;
  confidence_tier: string;
  status: string;
  edited_body: string | null;
  reviewed_at: string | null;
  created_at: string;
}

export async function ingestSignals(software_id: string, source_type?: string) {
  const res = await apiClient.post<{ ingested_count: number; software_id: string }>(
    '/signals/ingest',
    { software_id, source_type },
  );
  return res.data;
}

export async function getSignalEvents(params?: {
  software_id?: string;
  source_type?: string;
  severity?: string;
  page?: number;
  per_page?: number;
}): Promise<SignalEventList> {
  const res = await apiClient.get<SignalEventList>('/signals/events', { params });
  return res.data;
}

export async function analyzeSignals(software_id: string, window_days = 30) {
  const res = await apiClient.post<{ status: string; software_id: string }>(
    '/signals/analyze',
    { software_id, window_days },
  );
  return res.data;
}

export async function getHealthScores(software_id?: string): Promise<HealthScore[]> {
  const res = await apiClient.get<HealthScore[]>('/signals/health-scores', {
    params: software_id ? { software_id } : undefined,
  });
  return res.data;
}

export async function getReviewDrafts(status?: string): Promise<ReviewDraft[]> {
  const res = await apiClient.get<ReviewDraft[]>('/signals/review-drafts', {
    params: status ? { status } : undefined,
  });
  return res.data;
}

export async function getReviewDraft(id: string): Promise<ReviewDraft> {
  const res = await apiClient.get<ReviewDraft>(`/signals/review-drafts/${id}`);
  return res.data;
}

export async function updateReviewDraft(
  id: string,
  data: { status: string; edited_body?: string },
): Promise<ReviewDraft> {
  const res = await apiClient.patch<ReviewDraft>(`/signals/review-drafts/${id}`, data);
  return res.data;
}

export async function sendReviewDraft(id: string) {
  const res = await apiClient.post<{ status: string; draft_id: string }>(
    `/signals/review-drafts/${id}/send`,
  );
  return res.data;
}

export interface StageSmoothnessMetrics {
  friction: number;
  recurrence: number;
  escalation: number;
  resolution: number;
  effort: number;
}

export interface TrajectoryStage {
  name: string;
  status: string;
  signal_count: number;
  smoothness_score: number | null;
  date_range: { start: string; end: string } | null;
  explanation: string;
  metrics: StageSmoothnessMetrics | null;
  metric_details: Record<string, string> | null;
  metric_confidence: Record<string, 'high' | 'low'> | null;
}

export interface BenchmarkComparison {
  average: number;
  median: number;
  percentile: number;
  peer_count: number;
}

export interface StageBenchmark extends BenchmarkComparison {
  metrics?: Record<string, BenchmarkComparison> | null;
}

export interface TrajectoryBenchmarks {
  category: string | null;
  peer_count: number;
  overall: BenchmarkComparison | null;
  stages: Record<string, StageBenchmark>;
}

export interface HealthScoreBenchmarks {
  category: string | null;
  peer_count: number;
  overall: BenchmarkComparison | null;
  categories: Record<string, BenchmarkComparison>;
}

export interface Trajectory {
  current_stage: string;
  stages: TrajectoryStage[];
  regression_detected: boolean;
  regression_detail: string | null;
  overall_smoothness: number;
  confidence: string;
  benchmarks: TrajectoryBenchmarks | null;
}

export async function getTrajectory(softwareId: string): Promise<Trajectory> {
  const res = await apiClient.get<Trajectory>('/signals/trajectory', {
    params: { software_id: softwareId },
  });
  return res.data;
}

// ---------------------------------------------------------------------------
// Hierarchical Summaries
// ---------------------------------------------------------------------------

export interface HealthSummaries {
  reliability?: string | null;
  performance?: string | null;
  fitness_for_purpose?: string | null;
  overall?: string | null;
}

export interface StageSummaries {
  friction?: string | null;
  recurrence?: string | null;
  escalation?: string | null;
  resolution?: string | null;
  effort?: string | null;
  overall?: string | null;
}

export interface TrajectorySummaries {
  stages?: Record<string, StageSummaries>;
  overall?: string | null;
}

export interface Summaries {
  health?: HealthSummaries | null;
  trajectory?: TrajectorySummaries | null;
}

export async function getSummaries(softwareId: string): Promise<Summaries | null> {
  const res = await apiClient.get<Summaries | null>('/signals/summaries', {
    params: { software_id: softwareId },
  });
  return res.data;
}

export async function getHealthScoreBenchmarks(softwareId: string): Promise<HealthScoreBenchmarks | null> {
  const res = await apiClient.get<HealthScoreBenchmarks | null>('/signals/health-score-benchmarks', {
    params: { software_id: softwareId },
  });
  return res.data;
}

export interface IssueRatePoint {
  date: string;
  count: number;
}

export interface IssueRateCommentary {
  trend: string;
  message: string;
}

export interface PeerIssueRate {
  category: string | null;
  peer_count: number;
  points: IssueRatePoint[];
}

export interface IssueRate {
  points: IssueRatePoint[];
  commentary: IssueRateCommentary;
  days_since_registration: number;
  peer: PeerIssueRate | null;
}

export async function getIssueRate(softwareId: string, stageTopic?: string): Promise<IssueRate> {
  const params: Record<string, string> = { software_id: softwareId };
  if (stageTopic) params.stage_topic = stageTopic;
  const res = await apiClient.get<IssueRate>('/signals/issue-rate', { params });
  return res.data;
}

export interface RecurrenceRatePoint {
  date: string;
  rate: number;
  recurring_count: number;
  total_threads: number;
  top_topics: string[];
}

export interface RecurrenceCommentary {
  trend: string;
  message: string;
}

export interface PeerRecurrenceRate {
  category: string | null;
  peer_count: number;
  points: IssueRatePoint[];
}

export interface RecurrenceRate {
  points: RecurrenceRatePoint[];
  commentary: RecurrenceCommentary;
  peer: PeerRecurrenceRate | null;
}

export async function getRecurrenceRate(softwareId: string, stageTopic?: string): Promise<RecurrenceRate> {
  const params: Record<string, string> = { software_id: softwareId };
  if (stageTopic) params.stage_topic = stageTopic;
  const res = await apiClient.get<RecurrenceRate>('/signals/recurrence-rate', { params });
  return res.data;
}

export interface ResolutionTimePoint {
  date: string;
  median_hours: number | null;
  p90_hours: number | null;
  pair_count: number;
  open_count: number;
}

export interface ResolutionTimeCommentary {
  trend: string;
  message: string;
}

export interface PeerResolutionTime {
  category: string | null;
  peer_count: number;
  points: ResolutionTimePoint[];
}

export interface ResolutionTimeCategoryData {
  category: string;
  points: ResolutionTimePoint[];
  commentary: ResolutionTimeCommentary;
  peer: PeerResolutionTime | null;
}

export interface ResolutionTime {
  categories: ResolutionTimeCategoryData[];
  days_since_registration: number;
}

export async function getResolutionTime(softwareId: string, stageTopic?: string): Promise<ResolutionTime> {
  const params: Record<string, string> = { software_id: softwareId };
  if (stageTopic) params.stage_topic = stageTopic;
  const res = await apiClient.get<ResolutionTime>('/signals/resolution-time', { params });
  return res.data;
}

// ---------------------------------------------------------------------------
// Vendor Responsiveness
// ---------------------------------------------------------------------------

export interface ResponsivenessPoint {
  date: string;
  median_lag_hours: number | null;
  p90_lag_hours: number | null;
  response_count: number;
  proactive_count: number;
  unanswered_count: number;
}

export interface ResponsivenessCommentary {
  trend: string;
  message: string;
}

export interface PeerResponsiveness {
  category: string | null;
  peer_count: number;
  points: ResponsivenessPoint[];
}

export interface VendorResponsiveness {
  points: ResponsivenessPoint[];
  commentary: ResponsivenessCommentary;
  days_since_registration: number;
  peer: PeerResponsiveness | null;
}

export async function getVendorResponsiveness(softwareId: string): Promise<VendorResponsiveness> {
  const res = await apiClient.get<VendorResponsiveness>('/signals/vendor-responsiveness', {
    params: { software_id: softwareId },
  });
  return res.data;
}

// ---------------------------------------------------------------------------
// Escalation Rate
// ---------------------------------------------------------------------------

export interface EscalationRatePoint {
  date: string;
  rate: number;
  escalation_count: number;
  total_threads: number;
  top_escalations: string[];
}

export interface EscalationCommentary {
  trend: string;
  message: string;
}

export interface PeerEscalationRate {
  category: string | null;
  peer_count: number;
  points: IssueRatePoint[];
}

export interface EscalationRate {
  points: EscalationRatePoint[];
  commentary: EscalationCommentary;
  peer: PeerEscalationRate | null;
}

export async function getEscalationRate(softwareId: string, stageTopic?: string): Promise<EscalationRate> {
  const params: Record<string, string> = { software_id: softwareId };
  if (stageTopic) params.stage_topic = stageTopic;
  const res = await apiClient.get<EscalationRate>('/signals/escalation-rate', { params });
  return res.data;
}

// ---------------------------------------------------------------------------
// Core vs Peripheral
// ---------------------------------------------------------------------------

export interface CorePeripheralPoint {
  date: string;
  peripheral_ratio: number;
  core_count: number;
  peripheral_count: number;
  total_count: number;
  top_peripheral_categories: string[];
}

export interface CorePeripheralCommentary {
  trend: string;
  message: string;
}

export interface PeerCorePeripheral {
  category: string | null;
  peer_count: number;
  points: IssueRatePoint[];
}

export interface CorePeripheral {
  points: CorePeripheralPoint[];
  commentary: CorePeripheralCommentary;
  peer: PeerCorePeripheral | null;
}

export async function getCorePeripheral(softwareId: string, stageTopic?: string): Promise<CorePeripheral> {
  const params: Record<string, string> = { software_id: softwareId };
  if (stageTopic) params.stage_topic = stageTopic;
  const res = await apiClient.get<CorePeripheral>('/signals/core-peripheral', { params });
  return res.data;
}

// ---------------------------------------------------------------------------
// Fitness for Purpose
// ---------------------------------------------------------------------------

export interface FitnessPoint {
  date: string;
  request_ratio: number;
  request_count: number;
  total_signals: number;
  repeat_count: number;
  unique_request_topics: number;
  fulfilled_count: number;
  total_request_threads: number;
  fulfillment_rate: number;
  top_repeats: string[];
}

export interface FitnessCommentary {
  trend: string;
  message: string;
}

export interface PeerFitness {
  category: string | null;
  peer_count: number;
  points: IssueRatePoint[];
}

export interface FitnessMetrics {
  points: FitnessPoint[];
  commentary: FitnessCommentary;
  peer: PeerFitness | null;
}

export async function getFitnessMetrics(softwareId: string): Promise<FitnessMetrics> {
  const res = await apiClient.get<FitnessMetrics>('/signals/fitness-metrics', {
    params: { software_id: softwareId },
  });
  return res.data;
}

// ---------------------------------------------------------------------------
// Fitness Events (timeline)
// ---------------------------------------------------------------------------

export interface FitnessEvent {
  date: string | null;
  summary: string;
  fitness_implication: string;
  severity: string;
  valence: 'negative' | 'positive' | 'neutral';
  status: 'open' | 'fulfilled' | 'fulfillment';
  source_type: string;
  event_type: string;
}

export interface FitnessEvents {
  events: FitnessEvent[];
}

export async function getFitnessEvents(softwareId: string): Promise<FitnessEvents> {
  const res = await apiClient.get<FitnessEvents>('/signals/fitness-events', {
    params: { software_id: softwareId },
  });
  return res.data;
}

// ---------------------------------------------------------------------------
// Reliability
// ---------------------------------------------------------------------------

export interface ReliabilityPoint {
  date: string;
  incident_count: number;
  weighted_density: number;
  mtbf_hours: number | null;
  extracted_downtime_hours: number | null;
  extracted_uptime_pct: number | null;
  extraction_count: number;
  top_incidents: string[];
}

export interface ReliabilityCommentary {
  trend: string;
  message: string;
}

export interface PeerReliability {
  category: string | null;
  peer_count: number;
  points: IssueRatePoint[];
}

export interface Reliability {
  points: ReliabilityPoint[];
  commentary: ReliabilityCommentary;
  peer: PeerReliability | null;
}

export async function getReliability(softwareId: string): Promise<Reliability> {
  const res = await apiClient.get<Reliability>('/signals/reliability', {
    params: { software_id: softwareId },
  });
  return res.data;
}

// ---------------------------------------------------------------------------
// Reliability Events (timeline)
// ---------------------------------------------------------------------------

export interface ReliabilityEvent {
  date: string | null;
  summary: string;
  reliability_implication: string;
  severity: string;
  severity_label: string;
  source_type: string;
  event_type: string;
  downtime_hours: number | null;
  uptime_pct: number | null;
}

export interface ReliabilityEvents {
  events: ReliabilityEvent[];
}

export async function getReliabilityEvents(softwareId: string): Promise<ReliabilityEvents> {
  const res = await apiClient.get<ReliabilityEvents>('/signals/reliability-events', {
    params: { software_id: softwareId },
  });
  return res.data;
}

// ---------------------------------------------------------------------------
// Performance – latency & rate-limiting complaints
// ---------------------------------------------------------------------------

export interface PerformancePoint {
  date: string;
  latency_count: number;
  rate_limit_count: number;
  total_signals: number;
  top_latency_issues: string[];
  top_rate_limit_issues: string[];
}

export interface PerformanceCommentary {
  trend: string;
  message: string;
}

export interface PeerPerformance {
  category: string | null;
  peer_count: number;
  points: IssueRatePoint[];
}

export interface PerformanceMetrics {
  points: PerformancePoint[];
  commentary: PerformanceCommentary;
  peer: PeerPerformance | null;
}

export async function getPerformanceMetrics(softwareId: string): Promise<PerformanceMetrics> {
  const res = await apiClient.get<PerformanceMetrics>('/signals/performance', {
    params: { software_id: softwareId },
  });
  return res.data;
}

// ---------------------------------------------------------------------------
// Performance Events (timeline)
// ---------------------------------------------------------------------------

export interface PerformanceEvent {
  date: string | null;
  summary: string;
  performance_implication: string;
  severity: string;
  category: 'latency' | 'rate-limit' | 'latency + rate-limit';
  source_type: string;
  event_type: string;
}

export interface PerformanceEvents {
  events: PerformanceEvent[];
}

export async function getPerformanceEvents(softwareId: string): Promise<PerformanceEvents> {
  const res = await apiClient.get<PerformanceEvents>('/signals/performance-events', {
    params: { software_id: softwareId },
  });
  return res.data;
}

// ---------------------------------------------------------------------------
// Friction Events (timeline)
// ---------------------------------------------------------------------------

export interface FrictionEvent {
  date: string | null;
  summary: string;
  friction_implication: string;
  severity: string;
  valence: 'negative' | 'positive';
  source_type: string;
  event_type: string;
  impact: string;
}

export interface FrictionEvents {
  events: FrictionEvent[];
}

export async function getFrictionEvents(softwareId: string, stageTopic?: string): Promise<FrictionEvents> {
  const params: Record<string, string> = { software_id: softwareId };
  if (stageTopic) params.stage_topic = stageTopic;
  const res = await apiClient.get<FrictionEvents>('/signals/friction-events', { params });
  return res.data;
}

export interface RecurrenceEvent {
  date: string | null;
  summary: string;
  recurrence_implication: string;
  severity: string;
  valence: 'negative' | 'positive';
  source_type: string;
  event_type: string;
  impact: string;
  incident_number: number;
  total_incidents: number;
  first_seen: string;
  thread_topic: string;
}

export interface RecurrenceEvents {
  events: RecurrenceEvent[];
}

export async function getRecurrenceEvents(softwareId: string, stageTopic?: string): Promise<RecurrenceEvents> {
  const params: Record<string, string> = { software_id: softwareId };
  if (stageTopic) params.stage_topic = stageTopic;
  const res = await apiClient.get<RecurrenceEvents>('/signals/recurrence-events', { params });
  return res.data;
}

export interface EscalationEvent {
  date: string | null;
  summary: string;
  escalation_implication: string;
  severity_from: string;
  severity_to: string;
  severity_label: string;
  source_type: string;
  event_type: string;
  thread_topic: string;
}

export interface EscalationEvents {
  events: EscalationEvent[];
}

export async function getEscalationEvents(softwareId: string, stageTopic?: string): Promise<EscalationEvents> {
  const params: Record<string, string> = { software_id: softwareId };
  if (stageTopic) params.stage_topic = stageTopic;
  const res = await apiClient.get<EscalationEvents>('/signals/escalation-events', { params });
  return res.data;
}

// Resolution events (timeline of resolved tickets with duration)
export interface ResolutionEvent {
  date: string | null;
  summary: string;
  resolution_implication: string;
  resolution_hours: number;
  resolution_label: string;
  speed_label: string;
  category: string;
  severity: string;
  source_type: string;
  event_type: string;
}

export interface ResolutionEvents {
  events: ResolutionEvent[];
}

export async function getResolutionEvents(softwareId: string, stageTopic?: string): Promise<ResolutionEvents> {
  const params: Record<string, string> = { software_id: softwareId };
  if (stageTopic) params.stage_topic = stageTopic;
  const res = await apiClient.get<ResolutionEvents>('/signals/resolution-events', { params });
  return res.data;
}

// Effort events (timeline of core vs peripheral classified events)
export interface EffortEvent {
  date: string | null;
  summary: string;
  effort_implication: string;
  classification: 'core' | 'peripheral';
  peripheral_category: string | null;
  severity: string;
  source_type: string;
  event_type: string;
}

export interface EffortEvents {
  events: EffortEvent[];
}

export async function getEffortEvents(softwareId: string, stageTopic?: string): Promise<EffortEvents> {
  const params: Record<string, string> = { software_id: softwareId };
  if (stageTopic) params.stage_topic = stageTopic;
  const res = await apiClient.get<EffortEvents>('/signals/effort-events', { params });
  return res.data;
}
