Windowing, late arrival and delivery semantics
Keyed by customer_id. The producer sends with key=customer_id, so Kafka
hashes that key and every transaction for a customer lands on the same
partition. One consumer therefore owns that customer's complete history and can
keep a correct rolling window in memory with no cross-consumer coordination.
This is also what makes the processor horizontally scalable to 3 instances (one
per partition) without changing any code.

Sliding, event-time windows. features() re-filters the customer's event
list on every call, including events where
(at_time - window_seconds) < event_time <= at_time. The window is anchored on
the message's own timestamp, not the consumer's clock, so the 24h backfill
behaves identically to live traffic and replaying the topic reproduces the same
features. A sliding window is used rather than tumbling because a card-testing
burst straddling a tumbling boundary would appear as two unremarkable groups.

Late arrival. Order is guaranteed only within a partition, so events can
arrive out of event-time order. Because the window is recomputed by filtering on
timestamp rather than by trusting list order, a late event is included in any
window covering its timestamp and nothing is dropped. Features already written
to Redis are not retroactively corrected; they are recomputed on the customer's
next transaction. Given a multi-hour window, the effect on the customer's
baseline is negligible.

At-least-once delivery. The consumer auto-commits offsets, so a crash
between processing and commit causes redelivery. update() appends
unconditionally, so a duplicated transaction is counted twice until it ages out
of the window. This is accepted rather than solved: the distortion is small,
short-lived and affects one customer. Making the processor idempotent would mean
keeping a bounded set of recently seen transaction_ids per customer and
skipping repeats; exactly-once would require manual offset commits with
transactional writes, or a state-store stream processor.