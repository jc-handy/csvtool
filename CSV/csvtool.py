import argparse, contextlib, os, re, shlex, sys
from functools import reduce
from textwrap import wrap
import CSV as csv
from handy import ProgInfo, die, shellify
from debug import DebugChannel
from pprint import pprint

prog = ProgInfo()

# Make sure stdin and stdout are friendly to UTF-8 content.
sys.stdin = open(sys.stdin.fileno(), mode="r", encoding="utf8", buffering=1)
sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf8", buffering=1)

dc = DebugChannel(False, label="D")

# The gibberish in the first part of the regular expression below
# is a string of international currency smbols taken from
# https://economictimes.indiatimes.com/definition/currency-symbol.
re_numeric = re.compile(
    r"[$€£¥₣₹ﺪﻛﺇ﷼₻₽₾₺₼₸₴₷฿원₫₮₯₱₳₵₲₪₰]?(?P<int>[,0-9]+)?(?:\.(?P<decimal>\d+)?)?$"
)


def numeric(x):
    """Return the numeric value of x if x can be interpreted as either
    integer or float. Otherwise, return the original value of x.

    >>> numeric('4')
    4
    >>> numeric('4.0000')
    4
    >>> numeric('3.25')
    3.25
    >>> numeric('testing')
    'testing'
    >>> numeric('$123,456.789')
    123456.789
    """

    y = x if isinstance(x, str) else str(x)
    m = re_numeric.match(y)
    if m:
        if y.startswith("$"):
            y = y[1:]
        if "," in y:
            y = y.replace(",", "")
    with contextlib.suppress(ValueError):
        return int(y)
    with contextlib.suppress(ValueError):
        y = float(y)
        if y.is_integer():
            y = int(y)
        return y
    return x


def width(x):
    "Return the number of characters required to express this value."

    if isinstance(x, str):
        w = len(x)
    else:
        w = len(str(x))

    return w


def parse_range(s):
    """Convert string list of ranges into a list of (n,m) range tuples."""

    ranges = [x.strip() for x in s.split(",")]
    f = []
    for r in ranges:
        r = r.split("-")
        if len(r) == 1:
            m = int(r[0])
            n = m - 1
        else:
            n, m = r
            if n == "":
                n = 0
            else:
                n = int(n) - 1
            if m == "":
                m = None
            else:
                m = int(m)
        f.append((n, m))
    return f


 # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
# Create writer classes for out shell and table output formats.

class ShellWriter(object):
    """This class has a writerow() method to mimic enough of the interface
    of csv.writer, but out writerow() outputs a line of shell environment
    variable assignment statements separated by semicolons rather than a
    line of csv output.

    For this class to do its job, the first call to writerow() must
    contain a list of variable names to be used for every subsequent call
    writerow()."""

    def __init__(self, outfile, **flags):
        """outfile is the open file we are to write data to. The following
        arguments are recognized:

          none_as holds the text to be used to represent None values in the
          output. The default is simply '', but setting it to something like
          'None', 'NULL', or 'N/A' is sometimes helpful.
        """

        self.outfile = outfile
        self.vars = None
        self.none_as = flags.get("none_as", "")

    def setHeadings(self, headings):
        self.vars = [str(h) for h in headings]

    def writerow(self, row):
        if not self.vars:
            self.setHeadings(row)
        else:
            # Replace None values with whatever's in self.none_as.
            r = []
            for val in row:
                if val == None:
                    val = self.none_as
                r.append(val)
            # Write our line of shell environment variable assignments.
            self.outfile.write(
                ";".join(
                    [
                        "%s=%s" % (var.replace(" ", "_"), shellify(val))
                        for var, val in zip(self.vars, r)
                    ]
                )
            )
            self.outfile.write("\n")

    def writerows(self, rows):
        for row in rows:
            self.writerow(row)


def tabfmt(val, width):
    if isinstance(val, int):
        return "%*d" % (width, val)
    if isinstance(val, float):
        return "%*f" % (width, val)
    return "%-*s" % (width, str(val))


class TableWriter(object):
    def __init__(self, outfile, **flags):
        """outfile is the open file we are to write data to. The following
        arguments are recognized:

          style     either "ascii" or "box" (the default).
          none_as   holds the text to be used to represent None values in
                    the output. The default is simply '', but setting it to
                    something like 'None', 'NULL', or 'N/A' is sometimes
                    helpful.
          col_sep   The column separator character in ASCII output.
                    (default=' | ')
          haed_sep  The line that separates the first heading line from the
                    remaining data lines in ASCII output. (default='-')
          markdown  True if this table is to be output as Markdown.
                    (default=False)

        """

        self.outfile = outfile
        self.none_as = flags.get("none_as", "")
        self.style = flags.get("style", "box")
        if self.style == "box":
            self.col_sep = flags.get("col_sep", " │ ")
            self.head_sep = flags.get("head_sep", "─")
        elif self.style == "ascii":
            self.col_sep = flags.get("col_sep", " | ")
            self.head_sep = flags.get("head_sep", "-")
        elif self.style == "nosep":
            self.col_sep = flags.get("col_sep", " ")
            self.head_sep = flags.get("head_sep", "")
        self.markdown = flags.get("markdown", False)
        self.data = []  # Our list of data rows.

    def writerow(self, row):
        """Only record rows in this writer. The writerows() method is what
        actually writes the output."""

        self.data.append([self.none_as if v is None else v for v in row])

    def writerows(self, rows=None):
        """This works just like the regular csv.reader.writerows() if the rows
        argument refers to data to be written. But if no row data it given,
        we assume all data has been accumulated, and it's time to write out
        the table. This latter behavior is specific to TableWriter instances."""

        if rows is not None:
            # Append the caller's rows to output.
            for row in rows:
                self.writerow(row)
        elif self.data:
            if self.markdown:
                # Write out tabular data as Markdown.
                for r in range(len(self.data)):
                    row = self.data[r]
                    self.outfile.write(
                        "| "
                        + (" | ".join([str(row[c]) for c in range(len(row))]))
                        + "\n"
                    )
                    # self.outfile.write((''.join(['| '+row[c] for c in range(len(row))]))+'\n')
                    if opt.heading_lines > 0 and r == opt.heading_lines - 1:
                        self.outfile.write("|-" * len(row) + "\n")
            else:
                # Compute the width each column requires.
                wid = [
                    reduce(max, [width(self.data[r][c]) for r in range(len(self.data))])
                    for c in range(len(self.data[0]))
                ]
                # Write out tabular data.
                for r in range(len(self.data)):
                    row = self.data[r]
                    self.outfile.write(
                        self.col_sep.join(
                            [tabfmt(row[c], wid[c]) for c in range(len(row))]
                        )
                        + "\n"
                    )
                    if opt.heading_lines > 0 and r < opt.heading_lines:
                        if self.style != "nosep":
                            # Output a line that separates our heading line(s) from the body of the data.
                            self.outfile.write(
                                self.col_sep.replace(" ", self.head_sep)
                                .replace("│", "┼")
                                .replace("|", "+")
                                .join([self.head_sep * wid[c] for c in range(len(row))])
                                + "\n"
                            )
            self.data = []


# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
 # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

# We need to preformat some of our help text.
description="""\
This command reads data from standard input in either CSV (by default), Excel,
or shell format and writes it to standard output as CSV (by default), shell, or
either of two tabular formats: table and markdown. The CSV dialects used for
reading and writing needn't be the same and can be specified using the --reader
(in the case of Form 1) and --writer options.

Regardless of which usage form is used, any data values given as command line
arguments supply a row of data that will be appear as the first line of output.
This is typically used to output column headings, (e.g.: 'First name' Last\\
name email account zipcode), but it could just as easily be a row of actual
data. Just in case it's not obvious, any data given on the command line in this
way is not CSV-formatted. It is parsed by your shell, so use proper escapes and
quoting to distinguish one argument (data value) from another.

The output format defaults to CSV (--outfmt=csv), but it can also be set to
shell, table, or markdown. If shell, each line of output is a list of
environment variable assignments separated by semicolons. This REQUIRES the
first line of input data to consist of column headings that are also valid
environment variable names. If --outfmt=table is used, consider using
--headings 1 (or 2 or whatever) to say how many lines of input should be
treated as column headings. (The default is 0.) "-box" (the default) or
"-ascii" can also be appended to "table" to determine whether box-drawing
characters or normal ASCII characters are used to separate one column from
another and heading rows from data rows. --outfmt=markdown is just like table
output, but output is Markdown-formatted.

FIELDSPEC Syntax: A FIELDSPEC is made up of one or more ranges separated by
commas. Each range is one of "N" (the Nth field), "N-" (from the Nth to the
last field), or "N-M" (from the Nth to the Mth field, inclusive). Fields are
counted beginning with 1.
"""
# This really ought to be handled in a help formatting class, but here we are.
description=[l.strip() for l in description.split('\n')]
paragraphs=[]
i=0
for j,l in enumerate(description):
    if description[j]:
        continue
    s=wrap(' '.join(description[i:j]),width=prog.term_width-1)
    paragraphs.append('\n'.join(s))
    i=j+1
else:
    if i<j:
        s=wrap(' '.join(description[i:j]),width=prog.term_width-1)
        paragraphs.append('\n'.join(s))
#pprint(paragraphs,100)
description=('\n\n'.join(paragraphs))
del paragraphs

def main():
    # Interpret the command line.
    ap = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
        usage="""
      Form 1: %(prog)s [OPTIONS] [value-1 ... value-n]
        Input MUST be formatted as parsable CSV.

      Form 2: %(prog)s --infmt=excel [--worksheet=WORKSHEET] [OPTIONS] [value-1 ... value-n]
        Input MUST be an Excel spreadsheet. The first worksheet will be used unless named.

      Form 3: %(prog)s --infmt=shell [OPTIONS] [value-1 ... value-n]
        Input MUST be lines of shell-escaped and -quoted values.""",
        description=description + '\n\n' + csv.CSV_DIALECT_DESCRIPTION
    )
    ap.add_argument(
        "--join",
        metavar="JOINSPEC",
        dest="join_fields",
        action="store",
        help="""Join the given field range into a single field separated by a single character. The first character of the JOINSPEC value is the field separator. The remainder of JOINSPEC is the same field range syntax (FIELDSPEC) described above. Also, --join renumbers fields as they are joined. So if "--join ' 1-2'" is given, fields 1 and 2 are joined as field 1, and any subsequent fields are renumbered beginning with 2. This is important to remember if you're also using the --keep option because --keep is evaluated after --join.""",
    )
    ap.add_argument(
        "--lambda",
        dest="func",
        action="store",
        default=None,
        help="""Give a lambda expression (minus the "lambda" keyword) accepting two arguments, row number (starting with 1) and row (as a list). The function must return either the row, possibly modified, or None, in which case the current row is discarded entirely, and processing continues with the new row.""",
    )
    ap.add_argument(
        "--keep",
        metavar="FIELDSPEC",
        action="store",
        help="""Output only these fields. See the "FIELDSPEC Syntax" section above. By default, all fields are kept (of course).""",
    )
    ap.add_argument(
        "--headings",
        metavar="N",
        dest="heading_lines",
        action="store",
        type=int,
        default=0,
        help="Set how many rows (lines) of heading data are in the input. (default: %(default)r)",
    )
    ap.add_argument(
        "--infmt",
        dest="infmt",
        action="store",
        choices=("csv", "excel", "shell"),
        default="csv",
        help="Set the input format. See the usage and description above for details. (default: %(default)r)",
    )
    ap.add_argument(
        "--reader",
        dest="reading",
        metavar="DIALECT",
        action="store",
        default=csv.DEFAULT_DIALECT_SPEC,
        help="""Set the CSV reader's dialect. See CSV DIALECT SYNTAX above. (default: %(default)r""",
    )
    ap.add_argument(
        "--outfmt",
        dest="outfmt",
        action="store",
        default="csv",
        help="Set either csv, shell, table, table-ascii, table-box, table-nosep, or markdown as the output format. See the usage and description above for details. (default: %(default)r)",
    )
    ap.add_argument(
        "--writer",
        dest="writing",
        metavar="DIALECT",
        action="store",
        default=csv.DEFAULT_DIALECT_SPEC,
        help="Set the CSV writer's dialect. See CSV DIALECT SYNTAX above. (default: %(default)r)",
    )
    ap.add_argument(
        "--worksheet",
        dest="worksheet",
        metavar="NAME_or_NUMBER",
        action="store",
        default=None,
        help="Give the name or number (starting with 0) of the worksheet to read if --excel was used. If not given, the first worksheet will be read.",
    )
    ap.add_argument(
        "--debug",
        dest="debug",
        action="store_true",
        default=False,
        help="Turn on debugging output.",
    )
    ap.add_argument(
        "--test",
        dest="test",
        action="store_true",
        default=False,
        help="Run internal tests (for debugging purposes only).",
    )
    ap.add_argument(
        "--help", "-h", action="help", help="Show this help message and exit."
    )
    ap.add_argument(
        "args",
        action="store",
        nargs="*",
        default=[],
        help="See the usage forms above. Command line arguments' meanings depend on what form is being used.",
    )
    opt = ap.parse_args()
    dc.enable(opt.debug)

    # Cook table output format specs a bit. (This is where opt.style comes from.)
    if opt.join_fields:
        opt.joinchar = opt.join_fields[0]
        opt.join_fields = parse_range(opt.join_fields[1:])
        # TODO Add logic to ensure opt.join_fields is in ascending order.
        opt.join_fields.reverse()  # Field joining is performed from right to left.
    else:
        opt.join_fields = []
    if opt.func:
        opt.func = eval(f"lambda {opt.func}")
    if opt.keep:
        opt.keep = parse_range(opt.keep)
    if opt.outfmt.startswith("table"):
        if opt.outfmt == "table":
            opt.style = "box"
        else:
            opt.style = opt.outfmt[5:]
            if not opt.style.startswith("-"):
                die(f"Bad value for --outfmt: {opt.outfmt!r}")
            opt.style = opt.style[1:]
            if opt.style not in ("ascii", "box", "nosep"):
                die(f"Bad value for --outfmt: {opt.outfmt!r}")
        opt.outfmt = "table"
    if opt.outfmt not in ("csv", "shell", "table", "markdown"):
        die(f"Bad value for --outfmt: {opt.outfmt!r}")

    opt.writing = csv.parse_dialect("custom_writer", opt.writing)

    if dc:
        dc("Options:").indent()
        dc(f"heading_lines={opt.heading_lines!r}")
        dc(f"infmt={opt.infmt!r}")
        dc(f"reading={opt.reading!r}")
        dc(f"writing={csv.dialect_string(opt.writing)!r}")
        dc(f"worksheet={opt.worksheet!r}")
        dc(f"test={opt.test!r}")
        dc(f"args={opt.args!r}")

    if opt.worksheet != None:
        if opt.infmt != "excel":
            op.error("--worksheet can only be used with --infmt=excel.")
        try:
            opt.worksheet = int(opt.worksheet)
        except:
            pass

    # Set up a reader for whatever type of input we're expecting.
    if opt.infmt == "csv":
        opt.reading = csv.parse_dialect("custom_reader", opt.reading)
        reader = csv.reader(sys.stdin, dialect=opt.reading)
    elif opt.infmt == "excel":
        try:
            # TODO: Consider replacing xlrd with openpyxl.
            import xlrd
        except:
            die("3rd-party Python module xlrd (required by --excel) cannot be loaded.")

        def xlsreader(filename, worksheet=0):
            """This is a generator function that returns one row at a time fromt
            the given Excel spreadsheet file. By default, the first worksteet (0)
            is the one that's used."""

            book = xlrd.open_workbook(filename)
            try:
                worksheet = int(worksheet)
            except:
                pass
            if isinstance(worksheet, int):
                try:
                    sheet = book.sheet_by_index(worksheet)
                except IndexError:
                    die(
                        "%s: worksheet %d not found in %s."
                        % (progname, worksheet, filename)
                    )
            else:
                try:
                    sheet = book.sheet_by_name(str(worksheet))
                except xlrd.biffh.XLRDError:
                    die(
                        "%s: worksheet %r not found in %s."
                        % (progname, str(worksheet), filename)
                    )
            r = 0
            while r < sheet.nrows:
                yield [x.value for x in sheet.row(r)]
                r += 1

        reader = xlsreader("/dev/stdin", opt.worksheet)
    elif opt.infmt == "shell":

        def shellreader(f):
            for line in f:
                if opt.writing.quoting == csv.QUOTE_NONNUMERIC:
                    row = [numeric(val) for val in shlex.split(line)]
                else:
                    row = shlex.split(line)
                yield row

        reader = shellreader(sys.stdin)
    else:
        die(f"Programming Error! Unknown input format: {opt.infmt!r}")

    # Set up our writer (not necessarily for CSV output).
    if opt.outfmt == "csv":
        writer = csv.writer(sys.stdout, dialect=opt.writing)
    elif opt.outfmt == "shell":
        writer = ShellWriter(sys.stdout)
    elif opt.outfmt == "markdown":
        writer = TableWriter(sys.stdout, markdown=True)
    elif opt.outfmt == "table":
        writer = TableWriter(sys.stdout, style=opt.style)
    else:
        die(f"Programming Error! Bad --outfmt value: {opt.outfmt!r}")

    # This is where unit testing is implemented.
    if opt.test:
        import doctest, io

        failed, total = doctest.testmod()
        if failed:
            sys.exit(1)
        sys.exit(0)

    # Output the CSV for our command line arguments, if any.
    if opt.args:
        writer.writerow(opt.args)

    # Read from the reader and write to the writer.
    i = 0
    for row in reader:
        i += 1
        if i > opt.heading_lines:
            # Leave heading rows in their raw form. For data rows, we do our best to
            # read numbers as numbers, even if they start with a currency symbol and
            # have interior commas. We also run any --lambda function on these rows.
            row = [numeric(v) for v in row]
            if opt.func:
                row = opt.func(i - opt.heading_lines, row)
                if row == None:
                    continue
        dc(f"row={row!r}")
        for n, m in opt.join_fields:
            row[n:m] = [opt.joinchar.join([x for x in row[n:m] if x])]
        if opt.keep:
            r = []
            for n, m in opt.keep:
                r.extend(row[n:m])
            row = r
        writer.writerow(row)
    if opt.outfmt in ("markdown", "table"):
        # All those calls to writer.writerow() above have accumulated the data
        # for our table. All that's left is to write it all out.
        writer.writerows()

    return None
