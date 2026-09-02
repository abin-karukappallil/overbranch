export interface SyncState {
  activeFile: string;
  activeLine: number;
  activePage: number;
  pdfReady: boolean;
  synctexReady: boolean;
  presentation: boolean;
}

export interface SyncTeXBackwardResult {
  file: string;
  line: number;
  column: number;
}

export interface SyncTeXForwardResult {
  page: number;
  x: number;
  y: number;
  h: number;
  v: number;
  width: number;
  height: number;
}
