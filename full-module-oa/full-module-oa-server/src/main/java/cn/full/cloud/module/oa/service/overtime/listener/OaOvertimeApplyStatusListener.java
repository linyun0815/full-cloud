package cn.full.cloud.module.oa.service.overtime.listener;

import cn.full.cloud.module.bpm.api.event.BpmProcessInstanceStatusEvent;
import cn.full.cloud.module.bpm.api.event.BpmProcessInstanceStatusEventListener;
import cn.full.cloud.module.oa.enums.BpmModelConstants;
import cn.full.cloud.module.oa.service.overtime.OaOvertimeApplyService;
import jakarta.annotation.Resource;
import cn.full.cloud.module.oa.enums.ApiConstants;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

/**
 * 加班申请审批结果监听器
 *
 * @author 芋道源码
 */
@RestController
@Validated
public class OaOvertimeApplyStatusListener extends BpmProcessInstanceStatusEventListener {

    @Resource
    private OaOvertimeApplyService overtimeApplyService;

    @Override
    public String getProcessDefinitionKey() {
        return BpmModelConstants.OVERTIME_APPLY;
    }

    @Override
    @PostMapping(ApiConstants.PREFIX + "/overtime-apply/update-audit-status") // 提供给 bpm-server RPC 调用
    protected void onEvent(@RequestBody BpmProcessInstanceStatusEvent event) {
        overtimeApplyService.updateOvertimeApplyStatus(Long.valueOf(event.getBusinessKey()), event.getStatus());
    }

}
