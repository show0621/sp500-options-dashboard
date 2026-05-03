Run python scanner.py
  
Traceback (most recent call last):
  File "/home/runner/work/sp500-options-dashboard/sp500-options-dashboard/scanner.py", line 85, in <module>
開始掃描 S&P 500...
    run_scanner()
  File "/home/runner/work/sp500-options-dashboard/sp500-options-dashboard/scanner.py", line 49, in run_scanner
    tickers = get_sp500_tickers()
  File "/home/runner/work/sp500-options-dashboard/sp500-options-dashboard/scanner.py", line 9, in get_sp500_tickers
    table = pd.read_html(url)[0]
  File "/opt/hostedtoolcache/Python/3.10.20/x64/lib/python3.10/site-packages/pandas/io/html.py", line 1240, in read_html
    return _parse(
  File "/opt/hostedtoolcache/Python/3.10.20/x64/lib/python3.10/site-packages/pandas/io/html.py", line 983, in _parse
    tables = p.parse_tables()
  File "/opt/hostedtoolcache/Python/3.10.20/x64/lib/python3.10/site-packages/pandas/io/html.py", line 249, in parse_tables
    tables = self._parse_tables(self._build_doc(), self.match, self.attrs)
  File "/opt/hostedtoolcache/Python/3.10.20/x64/lib/python3.10/site-packages/pandas/io/html.py", line 806, in _build_doc
    raise e
  File "/opt/hostedtoolcache/Python/3.10.20/x64/lib/python3.10/site-packages/pandas/io/html.py", line 785, in _build_doc
    with get_handle(
  File "/opt/hostedtoolcache/Python/3.10.20/x64/lib/python3.10/site-packages/pandas/io/common.py", line 728, in get_handle
    ioargs = _get_filepath_or_buffer(
  File "/opt/hostedtoolcache/Python/3.10.20/x64/lib/python3.10/site-packages/pandas/io/common.py", line 384, in _get_filepath_or_buffer
    with urlopen(req_info) as req:
  File "/opt/hostedtoolcache/Python/3.10.20/x64/lib/python3.10/site-packages/pandas/io/common.py", line 289, in urlopen
    return urllib.request.urlopen(*args, **kwargs)
  File "/opt/hostedtoolcache/Python/3.10.20/x64/lib/python3.10/urllib/request.py", line 216, in urlopen
    return opener.open(url, data, timeout)
  File "/opt/hostedtoolcache/Python/3.10.20/x64/lib/python3.10/urllib/request.py", line 525, in open
    response = meth(req, response)
  File "/opt/hostedtoolcache/Python/3.10.20/x64/lib/python3.10/urllib/request.py", line 634, in http_response
    response = self.parent.error(
  File "/opt/hostedtoolcache/Python/3.10.20/x64/lib/python3.10/urllib/request.py", line 563, in error
    return self._call_chain(*args)
  File "/opt/hostedtoolcache/Python/3.10.20/x64/lib/python3.10/urllib/request.py", line 496, in _call_chain
    result = func(*args)
  File "/opt/hostedtoolcache/Python/3.10.20/x64/lib/python3.10/urllib/request.py", line 643, in http_error_default
    raise HTTPError(req.full_url, code, msg, hdrs, fp)
urllib.error.HTTPError: HTTP Error 403: Forbidden
Error: Process completed with exit code 1.
