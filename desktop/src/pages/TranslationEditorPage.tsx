import { useCallback, useEffect, useState, type CSSProperties, type ReactNode } from 'react';
import { open } from '@tauri-apps/plugin-dialog';
import { PageHeader } from '../components/PageHeader';
import { Panel } from '../components/Panel';
import { Button } from '../components/Button';
import { EmptyState, InlineFeedback, LoadingState } from '../components/page-state';
import { speakerHue, speakerStyle } from '../lib/speaker';
import {
  PipelineApiError,
  compactCacheLogs,
  fetchCacheEntries,
  fetchCacheFiles,
  fetchPipelineToken,
  rebuildCacheOutput,
  setProblemStatus,
  subscribePipelineEvents,
  updateCacheEntry,
  type CacheEntriesPage,
  type CacheEntry,
  type CacheFileSummary,
} from '../lib/pipeline';

const PAGE_SIZE = 200;

function escapeControlChars(text: string): string {
  return text.replace(/\r/g, '\\r').replace(/\n/g, '\\n');
}

function unescapeControlChars(text: string): string {
  return text.replace(/\\r/g, '\r').replace(/\n/g, '\\n');
}

/** 搜索高亮(与上游缓存页同款交互) */
function HighlightText({ text, query }: { text: string; query: string }) {
  if (!query) return <>{text}</>;
  const lower = text.toLowerCase();
  const qLower = query.toLowerCase();
  const parts: ReactNode[] = [];
  let lastIdx = 0;
  let searchFrom = 0;
  while (searchFrom <= lower.length) {
    const found = lower.indexOf(qLower, searchFrom);
    if (found === -1) break;
    if (found > lastIdx) parts.push(text.slice(lastIdx, found));
    parts.push(<mark key={found} className="search-highlight">{text.slice(found, found + query.length)}</mark>);
    lastIdx = found + query.length;
    searchFrom = lastIdx;
  }
  if (lastIdx < text.length) parts.push(text.slice(lastIdx));
  return <>{parts}</>;
}

type RowState = { dirty: boolean; saving: boolean; saved: boolean; error: string };

export function TranslationEditorPage() {
  const [ready, setReady] = useState(false);
  const [loadingFiles, setLoadingFiles] = useState(false);
  const [loadingEntries, setLoadingEntries] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [projectDir, setProjectDir] = useState('');
  const [files, setFiles] = useState<CacheFileSummary[]>([]);
  const [activeFile, setActiveFile] = useState('');
  const [editable, setEditable] = useState(true);
  const [page, setPage] = useState<CacheEntriesPage | null>(null);
  const [sidebarTab, setSidebarTab] = useState<'files' | 'problems'>('files');
  const [filter, setFilter] = useState<{ q: string; locked: boolean; problem: boolean; untranslated: boolean }>({
    q: '',
    locked: false,
    problem: false,
    untranslated: false,
  });
  const [rows, setRows] = useState<Record<number, CacheEntry>>({});
  const [rowState, setRowState] = useState<Record<number, RowState>>({});
  const [jobLog, setJobLog] = useState<string[]>([]);
  const [jobRunning, setJobRunning] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await fetchPipelineToken();
        if (!cancelled) setReady(true);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const refreshFiles = useCallback(async (dir: string) => {
    try {
      const data = await fetchCacheFiles(dir);
      setFiles(data.files);
      setEditable(data.editable);
      return data.files;
    } catch (err) {
      setError(err instanceof PipelineApiError ? `${err.code}: ${err.message}` : String(err));
      return [];
    }
  }, []);

  const loadPage = useCallback(
    async (dir: string, file: string, f: typeof filter, pageNum = 1) => {
      if (!dir || !file) return;
      setLoadingEntries(true);
      try {
        const data = await fetchCacheEntries(dir, file, {
          q: f.q || undefined,
          locked: f.locked ? true : undefined,
          problem: f.problem ? true : undefined,
          untranslated: f.untranslated ? true : undefined,
          page: pageNum,
          page_size: PAGE_SIZE,
        });
        setPage(data);
        setRows(Object.fromEntries(data.entries.map((entry) => [entry.index, entry])));
        setRowState({});
        setError('');
      } catch (err) {
        setRowState({});
        setPage(null);
        setError(
          err instanceof PipelineApiError
            ? `[${err.code}] ${err.message}`
            : String(err),
        );
      } finally {
        setLoadingEntries(false);
      }
    },
    [],
  );

  const loadProject = useCallback(
    async (dir: string) => {
      setProjectDir(dir);
      setError('');
      setActiveFile('');
      setPage(null);
      setLoadingFiles(true);
      const list = await refreshFiles(dir);
      setLoadingFiles(false);
      if (list.length > 0) {
        setActiveFile(list[0].name);
        void loadPage(dir, list[0].name, filter);
      }
    },
    [refreshFiles, loadPage, filter],
  );

  const handleBrowseProject = useCallback(async () => {
    const selected = await open({ directory: true });
    if (typeof selected === 'string') void loadProject(selected);
  }, [loadProject]);

  const handlePickFile = useCallback(
    (name: string) => {
      setActiveFile(name);
      void loadPage(projectDir, name, filter);
    },
    [projectDir, loadPage, filter],
  );

  const handleFilterChange = useCallback(
    (patch: Partial<typeof filter>) => {
      const next = { ...filter, ...patch };
      setFilter(next);
      void loadPage(projectDir, activeFile, next);
    },
    [filter, projectDir, activeFile, loadPage],
  );

  const saveRow = useCallback(
    async (entry: CacheEntry, patch: { pre_dst?: string; locked?: boolean }) => {
      setRowState((prev) => ({
        ...prev,
        [entry.index]: { dirty: false, saving: true, saved: false, error: '' },
      }));
      try {
        await updateCacheEntry({
          project: projectDir,
          file: activeFile,
          index: entry.index,
          pre_src: entry.pre_src,
          ...patch,
        });
        setRows((prev) => ({
          ...prev,
          [entry.index]: { ...prev[entry.index], ...patch } as CacheEntry,
        }));
        setRowState((prev) => ({
          ...prev,
          [entry.index]: { dirty: false, saving: false, saved: true, error: '' },
        }));
      } catch (err) {
        setRowState((prev) => ({
          ...prev,
          [entry.index]: {
            dirty: true,
            saving: false,
            saved: false,
            error: err instanceof PipelineApiError ? `${err.code}: ${err.message}` : String(err),
          },
        }));
      }
    },
    [projectDir, activeFile],
  );

  const cycleProblemStatus = useCallback(
    async (entry: CacheEntry) => {
      const next =
        entry.problem_status === ''
          ? 'confirmed'
          : entry.problem_status === 'confirmed'
            ? 'ignored'
            : '';
      try {
        await setProblemStatus({
          project: projectDir,
          file: activeFile,
          index: entry.index,
          status: next,
        });
        setRows((prev) => ({
          ...prev,
          [entry.index]: { ...prev[entry.index], problem_status: next } as CacheEntry,
        }));
      } catch (err) {
        setError(err instanceof PipelineApiError ? `${err.code}: ${err.message}` : String(err));
      }
    },
    [projectDir, activeFile],
  );

  // SSE:重建输出等后台任务的事件流
  useEffect(() => {
    if (!ready) return () => undefined;
    return subscribePipelineEvents(
      (event) => {
        if (event.event === 'log') {
          setJobLog((prev) => [...prev.slice(-50), `[${event.data.step}] ${event.data.message}`]);
        } else if (event.event === 'job_started') {
          setJobRunning(true);
        } else if (event.event === 'job_done') {
          setJobRunning(false);
          setJobLog((prev) => [...prev, '完成 ✓']);
          void refreshFiles(projectDir);
        } else if (event.event === 'job_failed') {
          setJobRunning(false);
          setJobLog((prev) => [
            ...prev,
            `失败 [${event.data.code}] ${event.data.message.split('\n')[0]}`,
          ]);
        }
      },
      () => undefined,
    );
  }, [ready, projectDir, refreshFiles]);

  const handleCompact = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      const { merged } = await compactCacheLogs(projectDir);
      setSuccess(`已合并 ${merged} 个翻译日志`);
      await refreshFiles(projectDir);
      void loadPage(projectDir, activeFile, filter);
    } catch (err) {
      setError(err instanceof PipelineApiError ? `${err.code}: ${err.message}` : String(err));
    } finally {
      setBusy(false);
    }
  }, [projectDir, refreshFiles, loadPage, activeFile, filter]);

  const handleRebuild = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      await rebuildCacheOutput(projectDir, files.some((f) => f.has_append));
      setSuccess('已提交重建输出任务,完成后译文将写回输出文件');
    } catch (err) {
      setError(err instanceof PipelineApiError ? `${err.code}: ${err.message}` : String(err));
    } finally {
      setBusy(false);
    }
  }, [projectDir, files]);

  const totalPages = page ? Math.max(1, Math.ceil(page.total / page.page_size)) : 1;
  const totalProblems = files.reduce((sum, f) => sum + f.problems, 0);
  const activeSummary = files.find((f) => f.name === activeFile);

  return (
    <div className="page translation-editor-page">
      <PageHeader
        title="双语对照编辑器"
        description="直接修改缓存中的译文并锁定;重建输出后生效。锁定条目在后续翻译中不会被覆盖。"
      />

      <Panel title="① 选择工程">
        <div className="patch-page__row">
          <input
            className="cache-search"
            value={projectDir}
            onChange={(event) => setProjectDir(event.target.value)}
            placeholder="汉化工程目录(如 游戏_patch)"
          />
          <Button onClick={() => void handleBrowseProject()}>浏览…</Button>
          <Button
            variant="secondary"
            disabled={!projectDir.trim()}
            onClick={() => void loadProject(projectDir.trim())}
          >
            加载缓存
          </Button>
        </div>
      </Panel>

      {error && (
        <InlineFeedback tone="error" title="操作失败" description={error} onDismiss={() => setError('')} />
      )}
      {success && (
        <InlineFeedback tone="success" title="操作成功" description={success} onDismiss={() => setSuccess('')} />
      )}

      {loadingFiles && <LoadingState title="正在加载缓存文件…" />}

      {!loadingFiles && files.length === 0 && projectDir && (
        <EmptyState
          title="该工程还没有翻译缓存"
          description="先在补丁工作台跑到「AI 翻译」步,缓存生成后即可在此校对。"
        />
      )}
      {!loadingFiles && files.length === 0 && !projectDir && (
        <EmptyState
          title="选择一个汉化工程"
          description="输入或浏览工程目录后点「加载缓存」。"
        />
      )}

      {page && activeFile && (
        <div className="cache-layout patch-editor-layout">
          <aside className="cache-layout__sidebar patch-editor-sidebar">
            <div className="cache-sidebar-tabs">
              <button
                type="button"
                className={`cache-sidebar-tab ${sidebarTab === 'files' ? 'cache-sidebar-tab--active' : ''}`}
                onClick={() => setSidebarTab('files')}
              >
                文件
              </button>
              <button
                type="button"
                className={`cache-sidebar-tab ${sidebarTab === 'problems' ? 'cache-sidebar-tab--active' : ''}`}
                onClick={() => setSidebarTab('problems')}
              >
                问题{totalProblems > 0 ? <span className="cache-sidebar-tab__badge">{totalProblems}</span> : ''}
              </button>
            </div>
            {sidebarTab === 'files' && (
              <div className="cache-file-list patch-editor-file-list">
                {files.map((file) => (
                  <button
                    type="button"
                    key={file.name}
                    className={`cache-file-item ${file.name === activeFile ? 'cache-file-item--active' : ''}`}
                    onClick={() => handlePickFile(file.name)}
                  >
                    <span className="cache-file-item__name">{file.name}</span>
                    <span className="cache-file-item__size">
                      {file.entries} 行{file.locked > 0 ? ` · 锁 ${file.locked}` : ''}
                      {file.problems > 0 ? ` · 问 ${file.problems}` : ''}
                      {file.untranslated > 0 ? ` · 未译 ${file.untranslated}` : ''}
                    </span>
                  </button>
                ))}
              </div>
            )}
            {sidebarTab === 'problems' && (
              <div className="cache-file-list patch-editor-file-list">
                {files.filter((f) => f.problems > 0).length === 0 ? (
                  <EmptyState title="没有标记问题的文件" />
                ) : (
                  files
                    .filter((f) => f.problems > 0)
                    .map((file) => (
                      <button
                        type="button"
                        key={file.name}
                        className={`cache-file-item ${file.name === activeFile ? 'cache-file-item--active' : ''}`}
                        onClick={() => {
                          handlePickFile(file.name);
                          setFilter((prev) => ({ ...prev, problem: true }));
                          void loadPage(projectDir, file.name, { ...filter, problem: true });
                        }}
                      >
                        <span className="cache-file-item__name">{file.name}</span>
                        <span className="cache-file-item__size">{file.problems} 个问题</span>
                      </button>
                    ))
                )}
              </div>
            )}
          </aside>

          <div className="cache-layout__main patch-editor-main">
            <div className="patch-editor-toolbar">
              <input
                className="cache-search patch-editor-search"
                value={filter.q}
                placeholder="搜索原文/译文/角色…(回车)"
                onChange={(event) => setFilter((prev) => ({ ...prev, q: event.target.value }))}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') void handleFilterChange({ q: filter.q });
                }}
              />
              <Button variant="secondary" onClick={() => void handleFilterChange({ q: filter.q })}>
                搜索
              </Button>
              <label className="patch-editor-check">
                <input
                  type="checkbox"
                  checked={filter.locked}
                  onChange={(event) => void handleFilterChange({ locked: event.target.checked })}
                />
                只看锁定
              </label>
              <label className="patch-editor-check">
                <input
                  type="checkbox"
                  checked={filter.problem}
                  onChange={(event) => void handleFilterChange({ problem: event.target.checked })}
                />
                只看问题
              </label>
              <label className="patch-editor-check">
                <input
                  type="checkbox"
                  checked={filter.untranslated}
                  onChange={(event) => void handleFilterChange({ untranslated: event.target.checked })}
                />
                只看未翻译
              </label>
              <span className="patch-editor-spacer" />
              <Button
                variant="secondary"
                disabled={busy || jobRunning || !editable}
                onClick={() => void handleCompact()}
                title="把中断翻译遗留的 .append 日志合并进缓存"
              >
                合并日志
              </Button>
              <Button
                disabled={busy || jobRunning || !editable}
                onClick={() => void handleRebuild()}
                title="从缓存重建 gt_output 与 work/translated(不调用 API)"
              >
                重建输出
              </Button>
            </div>

            <div className="patch-editor-meta">
              <span className="cache-card__pill cache-card__pill--engine">{activeFile}</span>
              <span className="patch-editor-meta__text">
                共 {page.stats.entries} 条 · 锁定 {page.stats.locked} · 问题 {page.stats.problems} ·
                未翻译 {page.stats.untranslated} · 筛选命中 {page.total}
              </span>
              {activeSummary?.has_append && (
                <span className="cache-card__pill cache-card__pill--problem">有未合并日志,请先合并</span>
              )}
              {!editable && (
                <span className="cache-card__pill cache-card__pill--problem">任务运行中,缓存只读</span>
              )}
            </div>

            {loadingEntries ? (
              <LoadingState title="正在加载条目…" />
            ) : (
              <div className="cache-card-list patch-editor-card-list">
                {page.entries.map((entry) => {
                  const row = rows[entry.index] ?? entry;
                  const state = rowState[entry.index];
                  const speaker = entry.name || '—';
                  const speakerPillStyle: CSSProperties | undefined =
                    speaker !== '—' ? speakerStyle(speaker) : undefined;
                  const statusPill = state?.error
                    ? { label: '保存失败', cls: 'cache-card__pill--problem' }
                    : state?.saving
                      ? { label: '保存中…', cls: 'cache-card__pill--engine' }
                      : state?.saved
                        ? { label: '已保存 ✓', cls: 'cache-card__pill--engine' }
                        : state?.dirty
                          ? { label: '未保存', cls: 'cache-card__pill--engine' }
                          : null;
                  return (
                    <article
                      key={entry.index}
                      className={`cache-card${entry.problem ? ' cache-card--problem' : ''}`}
                    >
                      <div className="cache-card__row">
                        <span className="cache-card__field-label">#{entry.index}</span>
                        {speaker !== '—' && (
                          <span className="cache-card__pill cache-card__pill--speaker" style={speakerPillStyle}>
                            {speaker}
                          </span>
                        )}
                        {entry.problem && (
                          <span className="cache-card__pill cache-card__pill--problem patch-editor-problem"
                            title={`${entry.problem}\n(点击切换:确认 → 忽略 → 清除)`}
                            role="button"
                            tabIndex={0}
                            onClick={() => void cycleProblemStatus(entry)}
                            onKeyDown={(event) => {
                              if (event.key === 'Enter' || event.key === ' ') void cycleProblemStatus(entry);
                            }}
                          >
                            {row.problem_status === 'ignored'
                              ? '已忽略'
                              : row.problem_status === 'confirmed'
                                ? '已确认'
                                : '问题'}
                          </span>
                        )}
                        {row.locked && (
                          <span className="cache-card__pill cache-card__pill--engine patch-editor-locked">🔒 已锁定</span>
                        )}
                        <div className="cache-card__spacer" />
                        {statusPill && (
                          <span className={`cache-card__pill ${statusPill.cls}`}>{statusPill.label}</span>
                        )}
                      </div>
                      <div className="cache-card__fields">
                        <div className="cache-card__field">
                          <span className="cache-card__field-label">原文</span>
                          <div className="cache-card__input-wrap">
                            <span className="cache-card__readonly-input" title={escapeControlChars(row.pre_src)}>
                              {filter.q
                                ? <HighlightText text={escapeControlChars(row.pre_src)} query={filter.q} />
                                : escapeControlChars(row.pre_src)}
                            </span>
                          </div>
                        </div>
                        <div className="cache-card__field">
                          <span className="cache-card__field-label">译文</span>
                          <div className="cache-card__input-wrap">
                            <input
                              className="cache-card__input cache-card__input--zh"
                              value={escapeControlChars(row.pre_dst)}
                              disabled={!editable}
                              onChange={(event) => {
                                const value = unescapeControlChars(event.target.value);
                                setRows((prev) => ({
                                  ...prev,
                                  [entry.index]: { ...row, pre_dst: value },
                                }));
                                setRowState((prev) => ({
                                  ...prev,
                                  [entry.index]: { dirty: true, saving: false, saved: false, error: '' },
                                }));
                              }}
                              onBlur={() => {
                                if (state?.dirty && row.pre_dst !== entry.pre_dst) {
                                  void saveRow(entry, { pre_dst: row.pre_dst, locked: true });
                                }
                              }}
                              onKeyDown={(event) => {
                                if (event.key === 'Enter') (event.target as HTMLInputElement).blur();
                              }}
                              placeholder="译文(修改保存后自动锁定)"
                              title={escapeControlChars(row.pre_dst)}
                            />
                          </div>
                        </div>
                      </div>
                    </article>
                  );
                })}
              </div>
            )}

            <div className="patch-editor-pager">
              <Button
                variant="secondary"
                disabled={(page?.page ?? 1) <= 1}
                onClick={() => void loadPage(projectDir, activeFile, filter, (page?.page ?? 1) - 1)}
              >
                ← 上一页
              </Button>
              <span className="patch-editor-meta__text">
                第 {page?.page ?? 1} / {totalPages} 页
              </span>
              <Button
                variant="secondary"
                disabled={(page?.page ?? 1) >= totalPages}
                onClick={() => void loadPage(projectDir, activeFile, filter, (page?.page ?? 1) + 1)}
              >
                下一页 →
              </Button>
            </div>
          </div>
        </div>
      )}

      {jobLog.length > 0 && (
        <Panel title="后台任务">
          <div className="patch-page__log">
            {jobLog.map((line, index) => (
              <div key={`${index}-${line.slice(0, 12)}`}>{line}</div>
            ))}
          </div>
        </Panel>
      )}
    </div>
  );
}
