import importlib
import importlib.util
import unittest


DONE = ('STATUS:20EC,EVENTS:0001,TRIGGER:0026,ARMED:0,HISTORY_READY:1,'
        'TRIGGERED:1,ABORTED:0,REASON:1,CTRL:0,PENDING:1,LENMODE:1,TIME:0,'
        'CFG_SAMPLES:100000,PRE:30,MODE:1,VTH:2500,VCMP:0,ITH:1500,ICMP:4,'
        'ENABLE:3,ACTIVE_PRE:30000,RATE:100000000,SAMPLES:100000,TOTAL:400000,'
        'BLOCKS:49,DDR_WRITE_BURSTS:20000,BURSTS_STABLE:1,HEX_CHARS:800000,'
        'GAP_MS:1000,GAP_LEFT_MS:0')


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('ad_host.v26_protocol'), 'V26 protocol not implemented')
        self.p = importlib.import_module('ad_host.v26_protocol')

    def test_configuration_exact_wire_and_lengths(self):
        config = self.p.AcquisitionSettings(1,100000,30,1,2500,0,1500,4,3,1000)
        self.assertEqual(config.command('CFG'), b'CFG 1,100000,30,1,2500,0,1500,4,3,1000\r')
        self.assertEqual(config.samples, 100000)
        self.assertEqual(config.pre_samples, 30000)
        self.assertEqual(self.p.AcquisitionSettings(length=200).samples, 20000000)
        self.assertEqual(self.p.AcquisitionSettings(len_mode=1,length=1,pre=100).pre_samples,1)

    def test_invalid_configuration_rejected_before_send(self):
        for changes in ({'length':0},{'length':201},{'len_mode':2},{'pre':101},
                        {'mode':1,'enable':0},{'vth':4096},{'ith':-1},{'vcmp':5},
                        {'gap_ms':600001},{'length':1.5},{'length':True}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                self.p.AcquisitionSettings(**changes)

    def test_status_bases_masks_and_reordered_fields(self):
        s=self.p.parse_tst(','.join(reversed(DONE.split(','))))
        self.assertEqual(s['STATUS'],0x20EC)
        self.assertEqual(s['TOTAL'],400000)
        self.assertTrue(self.p.can_get(s)); self.assertFalse(self.p.can_arm(s))
        s['STATUS']|=0x1000
        self.assertFalse(self.p.can_get(s))
        s.update(STATUS=0x2461,PENDING=0)
        self.assertTrue(self.p.can_arm(s))

    def test_metadata_cross_checks_and_pre100(self):
        s=self.p.parse_tst(DONE); self.p.validate_record(s)
        for key,value in [('TOTAL',4),('HEX_CHARS',800001),('ACTIVE_PRE',100001),('RATE',56000000),('SAMPLES',0),('BLOCKS',48)]:
            bad=dict(s);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError): self.p.validate_record(bad)
        s.update(ACTIVE_PRE=100000);self.p.validate_record(s)

    def test_force_requires_known_manual_active_configuration(self):
        s=self.p.parse_tst(DONE);s.update(STATUS=0x2062,ARMED=1,HISTORY_READY=1,TRIGGERED=0)
        manual=self.p.AcquisitionSettings(mode=0)
        self.assertTrue(self.p.can_force(s,manual))
        self.assertFalse(self.p.can_force(s,None))
        self.assertFalse(self.p.can_force(s,self.p.AcquisitionSettings(mode=1)))
        s['HISTORY_READY']=0;self.assertFalse(self.p.can_force(s,manual))

    def test_release_respects_occupied_read_block(self):
        s=self.p.parse_tst(DONE);self.assertTrue(self.p.can_release(s))
        s['STATUS']|=0x100;self.assertFalse(self.p.can_release(s))

    def test_fst_set_comma(self):
        f=self.p.parse_fst('ID:ADFC,VER:0200,INIT:1,IERR:0,SET:10,1,HCLK:168000000,SDCLK:56000000')
        self.assertEqual(f['SET'],'10,1')

    def test_status_missing_duplicate_and_invalid_fields(self):
        for text in (DONE+',STATUS:2061',DONE.replace('CTRL:0,',''),DONE.replace('TOTAL:400000','TOTAL:0x400000')):
            with self.subTest(text=text),self.assertRaises(ValueError): self.p.parse_tst(text)
        self.assertNotIn('GAP_LEFT_MS',self.p.parse_tst(DONE.rsplit(',GAP_MS',1)[0]))

if __name__=='__main__':unittest.main()
