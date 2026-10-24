% pkareport.cls — Lớp tài liệu cho báo cáo chuyên đề nghiên cứu (Đại học Phenikaa).
% Mô phỏng định dạng của "Báo cáo - CDNC1.docx":
%   A4; lề trên 3 cm, dưới 3 cm, trái 3.5 cm, phải 2 cm; Times New Roman 13 pt;
%   giãn dòng 1.5; căn đều hai bên; chương 14 pt in đậm, viết hoa, căn giữa;
%   mục cấp 2 in đậm; mục cấp 3 in đậm nghiêng; chú thích hình/bảng 11 pt in nghiêng
%   đặt dưới hình/bảng; bìa có khung viền.
% Biên dịch bằng XeLaTeX (Overleaf: Menu -> Compiler -> XeLaTeX; file latexmkrc kèm theo
% cũng đặt sẵn XeLaTeX).
\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{pkareport}[2026/10/21 Bao cao chuyen de nghien cuu - Phenikaa]
\LoadClass[a4paper,12pt,oneside]{report}

\RequirePackage{iftex}
\ifXeTeX\else\ifLuaTeX\else
  \ClassError{pkareport}{Can bien dich bang XeLaTeX hoac LuaLaTeX}%
  {Overleaf: Menu -> Settings -> Compiler -> XeLaTeX.}
\fi\fi

% ---------------- Phông chữ ----------------
\RequirePackage{amsmath,amssymb,amsthm}
\RequirePackage{newtxmath}
\RequirePackage[no-math]{fontspec}
% TeX Gyre Termes: bản tương đương Times New Roman, có đủ dấu tiếng Việt, có sẵn trên Overleaf.
\setmainfont{texgyretermes}[
  Extension=.otf, UprightFont=*-regular, BoldFont=*-bold,
  ItalicFont=*-italic, BoldItalicFont=*-bolditalic]
\setmonofont{lmmono10}[Extension=.otf, UprightFont=*-regular, ItalicFont=*-italic,
  BoldFont=lmmonolt10-bold, BoldItalicFont=lmmonolt10-boldoblique, Scale=0.95]

% Cỡ chữ: thân bài 13 pt như bản Word.
\renewcommand\normalsize{\@setfontsize\normalsize{13pt}{15.6pt}%
  \abovedisplayskip 8pt plus 2pt minus 4pt
  \abovedisplayshortskip 2pt plus 2pt
  \belowdisplayshortskip 6pt plus 2pt minus 2pt
  \belowdisplayskip \abovedisplayskip}
\renewcommand\small{\@setfontsize\small{11pt}{13.2pt}}
\renewcommand\footnotesize{\@setfontsize\footnotesize{10pt}{12pt}}
\renewcommand\large{\@setfontsize\large{14pt}{16.8pt}}
\normalsize

% ---------------- Trang ----------------
\RequirePackage[a4paper,top=3cm,bottom=3cm,left=3.5cm,right=2cm,
  headheight=14pt,footskip=1.2cm]{geometry}
\RequirePackage{setspace}
\setstretch{1.43}            % ~ "1.5 lines" của Word với chữ 13 pt
\setlength{\parindent}{0pt}
\setlength{\parskip}{3pt plus 1pt}
\hyphenpenalty=10000 \exhyphenpenalty=10000 % tiếng Việt không ngắt âm tiết
\emergencystretch=3em
\pagestyle{plain}
\raggedbottom

% ---------------- Gói chung ----------------
\RequirePackage{graphicx}
\RequirePackage{xcolor}
\RequirePackage{booktabs,array,multirow,longtable,tabularx}
\RequirePackage{enumitem}
\setlist{nosep,leftmargin=1.6em,itemsep=2pt}
\RequirePackage{tikz}
\usetikzlibrary{calc,positioning,arrows.meta,shapes.misc,fit,backgrounds}
\RequirePackage{float}
\RequirePackage{algorithm}
\RequirePackage[noend]{algpseudocode}
\RequirePackage[font={small,it},labelfont={small,it},labelsep=period,
  justification=centering,skip=5pt]{caption}
\RequirePackage{titlesec}
\RequirePackage{titletoc}
\RequirePackage[hidelinks,bookmarksnumbered]{hyperref}

% ---------------- Tên gọi tiếng Việt ----------------
\renewcommand{\contentsname}{MỤC LỤC}
\renewcommand{\listfigurename}{DANH MỤC HÌNH VẼ}
\renewcommand{\listtablename}{DANH MỤC BẢNG BIỂU}
\renewcommand{\bibname}{TÀI LIỆU THAM KHẢO}
\renewcommand{\figurename}{Hình}
\renewcommand{\tablename}{Bảng}
\renewcommand{\chaptername}{CHƯƠNG}
\renewcommand{\appendixname}{PHỤ LỤC}
\floatname{algorithm}{Thuật toán}
\renewcommand{\listalgorithmname}{DANH MỤC THUẬT TOÁN}
\renewcommand{\proofname}{Chứng minh}

% Đánh số theo chương: Bảng 5.1, Hình 4.2, (3.1); thuật toán đánh số liên tục như bản Word.
\renewcommand{\thetable}{\thechapter.\arabic{table}}
\renewcommand{\thefigure}{\thechapter.\arabic{figure}}
\renewcommand{\theequation}{\thechapter.\arabic{equation}}
\captionsetup[table]{position=below}

% Thuật toán: chú thích đặt dưới, khung kẻ trên/dưới như khối mã trong bản Word.
\floatstyle{plain}
\restylefloat{algorithm}
\algrenewcommand\algorithmicrequire{\textbf{Đầu vào:}}
\algrenewcommand\algorithmicensure{\textbf{Đầu ra:}}
\algrenewcommand\alglinenumber[1]{\footnotesize #1:}
\newenvironment{algobox}{\par\small\setstretch{1.15}\noindent\rule{\linewidth}{0.6pt}\vspace{-4pt}}%
  {\vspace{-6pt}\noindent\rule{\linewidth}{0.6pt}\par}

% ---------------- Tiêu đề chương / mục ----------------
\setcounter{secnumdepth}{2}
\setcounter{tocdepth}{2}
\titleformat{\chapter}[block]
  {\centering\bfseries\large\setstretch{1.3}}{\chaptername\ \thechapter:}{0.35em}{}
\titleformat{name=\chapter,numberless}[block]
  {\centering\bfseries\large\setstretch{1.3}}{}{0pt}{}
\titlespacing*{\chapter}{0pt}{-6pt}{14pt}
\titleformat{\section}{\bfseries\normalsize}{\thesection.}{0.35em}{}
\titlespacing*{\section}{0pt}{8pt}{3pt}
\titleformat{\subsection}{\bfseries\itshape\normalsize}{\thesubsection.}{0.35em}{}
\titlespacing*{\subsection}{0pt}{6pt}{2pt}
\titleformat{\subsubsection}[runin]{\itshape\normalsize}{}{0pt}{}[.]
\titlespacing*{\subsubsection}{0pt}{4pt}{0.5em}
\renewcommand{\paragraph}[1]{\par\smallskip\noindent\textbf{#1}\hspace{0.5em}}

% ---------------- Mục lục và các danh mục ----------------
\newcommand{\tocdots}{\titlerule*[0.45pc]{.}\contentspage}
\titlecontents{chapter}[0pt]{\addvspace{2pt}\bfseries}
  {\chaptername\ \thecontentslabel: }{}{\tocdots}
\titlecontents{section}[1.0em]{\bfseries}{\thecontentslabel. }{}{\tocdots}
\titlecontents{subsection}[2.0em]{\bfseries\itshape}{\thecontentslabel. }{}{\tocdots}
\titlecontents{figure}[0pt]{}{\figurename~\thecontentslabel. }{}{\tocdots}
\titlecontents{table}[0pt]{}{\tablename~\thecontentslabel. }{}{\tocdots}
\titlecontents{algorithm}[0pt]{}{Thuật toán~\thecontentslabel. }{}{\tocdots}

% Chương không đánh số (mục lục, tóm tắt, tài liệu tham khảo...) và ghi vào mục lục.
\newcommand{\chuongkhongso}[1]{%
  \chapter*{#1}\phantomsection\addcontentsline{toc}{chapter}{#1}}
\renewcommand{\tableofcontents}{\chapter*{\contentsname}%
  \phantomsection\addcontentsline{toc}{chapter}{\contentsname}\@starttoc{toc}}
\renewcommand{\listoffigures}{\chuongkhongso{\listfigurename}\@starttoc{lof}}
\renewcommand{\listoftables}{\chuongkhongso{\listtablename}\@starttoc{lot}}
\renewcommand{\listofalgorithms}{\chuongkhongso{\listalgorithmname}\@starttoc{loa}}

% ---------------- Định nghĩa, mệnh đề ----------------
\newtheoremstyle{pkadef}{5pt}{5pt}{\upshape}{}{\bfseries\itshape}{.}{0.4em}
  {\thmname{#1}\thmnumber{ #2}\thmnote{ (#3)}}
\theoremstyle{pkadef}
\newtheorem{dinhnghia}{Định nghĩa}[chapter]
\newtheorem{baitoan}{Bài toán}[chapter]
\newtheorem{nhanxet}{Nhận xét}[chapter]
\newtheorem{menhde}{Mệnh đề}[chapter]

% ---------------- Danh mục từ viết tắt ----------------
\newenvironment{vietat}{\chuongkhongso{DANH MỤC TỪ VIẾT TẮT}%
  \begin{center}\setstretch{1.1}\begin{longtable}{|p{0.17\linewidth}|p{0.74\linewidth}|}\hline}%
  {\end{longtable}\end{center}}
\newcommand{\vt}[2]{#1 & #2 \\ \hline}

% ---------------- Tài liệu tham khảo ----------------
\renewenvironment{thebibliography}[1]{%
  \chuongkhongso{\bibname}%
  \list{\@biblabel{\@arabic\c@enumiv}}%
    {\settowidth\labelwidth{\@biblabel{#1}}\leftmargin\labelwidth
     \advance\leftmargin\labelsep\usecounter{enumiv}%
     \let\p@enumiv\@empty\renewcommand\theenumiv{\@arabic\c@enumiv}%
     \itemsep 2pt}\setstretch{1.2}\sloppy}%
  {\endlist}

% ---------------- Trang bìa ----------------
\newcommand{\coquan}[1]{\def\@coquan{#1}}
\newcommand{\truong}[1]{\def\@truong{#1}}
\newcommand{\loaibaocao}[1]{\def\@loaibaocao{#1}}
\newcommand{\tendetai}[1]{\def\@tendetai{#1}}
\newcommand{\phanbaocao}[1]{\def\@phanbaocao{#1}}
\newcommand{\gvhd}[1]{\def\@gvhd{#1}}
\newcommand{\hocvien}[1]{\def\@hocvien{#1}}
\newcommand{\mahv}[1]{\def\@mahv{#1}}
\newcommand{\khoa}[1]{\def\@khoa{#1}}
\newcommand{\noithoigian}[1]{\def\@noithoigian{#1}}
\newcommand{\logo}[1]{\def\@logo{#1}}
% Báo cáo nhóm (ScholarLens): \tennhom{Nhóm 2} và \nhom{<các dòng: Họ tên & MHV \\>}.
% Khi \nhom để trống, bìa dùng dòng Học viên / MHV như bản gốc.
\newcommand{\tennhom}[1]{\def\@tennhom{#1}}
\newcommand{\nhom}[1]{\def\@nhom{#1}}
\coquan{BỘ GIÁO DỤC VÀ ĐÀO TẠO}\truong{ĐẠI HỌC PHENIKAA}\loaibaocao{CHUYÊN ĐỀ NGHIÊN CỨU}
\tendetai{}\phanbaocao{}\gvhd{}\hocvien{}\mahv{}\khoa{}\noithoigian{}\logo{}\tennhom{}\nhom{}

\newcommand{\taobia}{%
  \begin{titlepage}
  \centering\setstretch{1.25}
  {\bfseries\@coquan\par}
  {\bfseries\underline{\@truong}\par}
  \ifx\@nhom\@empty\vspace{1.2cm}\else\vspace{0.8cm}\fi
  \ifx\@logo\@empty\else\includegraphics[width=4.6cm]{\@logo}\par\fi
  \ifx\@nhom\@empty\vspace{1.3cm}\else\vspace{0.8cm}\fi
  {\bfseries BÁO CÁO\par \@loaibaocao\par}
  \ifx\@nhom\@empty\vspace{1.4cm}\else\vspace{0.9cm}\fi
  {\bfseries\large\setstretch{1.3}\@tendetai\par}
  \ifx\@phanbaocao\@empty\else\vspace{0.6cm}{\bfseries\itshape\@phanbaocao\par}\fi
  \ifx\@nhom\@empty
    \vspace{1.6cm}
    \begin{tabular}{@{}l@{}}
      \textbf{Giảng viên hướng dẫn:} \@gvhd\\
      \textbf{Học viên:} \@hocvien\hspace{1.6cm}\textbf{MHV:} \@mahv\\
      \textbf{Khóa:} \@khoa
    \end{tabular}\par
  \else
    \vspace{1.0cm}
    \begin{tabular}{@{}l@{\hspace{1.2cm}}l@{}}
      \multicolumn{2}{@{}l@{}}{\textbf{Giảng viên hướng dẫn:} \@gvhd}\\[4pt]
      \multicolumn{2}{@{}l@{}}{\textbf{Nhóm thực hiện:} \@tennhom}\\
      \@nhom
      \multicolumn{2}{@{}l@{}}{\textbf{Khóa:} \@khoa}
    \end{tabular}\par
  \fi
  \vfill
  {\bfseries\@noithoigian\par}
  \vspace*{0.2cm}
  \begin{tikzpicture}[remember picture,overlay]
    \draw[line width=2.2pt]
      ($(current page.north west)+(3.0cm,-2.0cm)$) rectangle ($(current page.south east)+(-1.6cm,2.2cm)$);
    \draw[line width=0.6pt]
      ($(current page.north west)+(3.15cm,-2.15cm)$) rectangle ($(current page.south east)+(-1.75cm,2.35cm)$);
  \end{tikzpicture}%
  \end{titlepage}
  \setcounter{page}{2}}

\endinput
