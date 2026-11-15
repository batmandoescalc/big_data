# Python with Hadoop Streaming for every MapReduce job

Mappers and reducers are standard-library Python scripts run through Hadoop
Streaming, not Java MapReduce classes. The study is about understanding the
algorithms, so each job must be short enough for a student to read, test on a
laptop with a plain pipe, and explain. The cost is Streaming's process and
text-serialization overhead, and code that must stay compatible with the
cluster's Python 3.9.
