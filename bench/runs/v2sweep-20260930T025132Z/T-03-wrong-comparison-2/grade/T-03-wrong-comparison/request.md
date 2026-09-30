Customers are supposed to be flipped to the enterprise tier automatically when the
billing webhook comes in, but it never triggers for real webhooks — the enterprise
branch just doesn't fire. The weird part: when I paste the same plan value into a
shell and check it by hand, it matches fine. I think something is wrong with how we
compare the plan string, maybe some identity-vs-equality thing? Not sure. Please make
webhook-driven plan detection work.
