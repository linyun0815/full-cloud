package cn.full.cloud.module.oa.service.leave.listener;

import cn.full.cloud.module.bpm.api.event.BpmProcessInstanceStatusEvent;
import cn.full.cloud.module.bpm.api.event.BpmProcessInstanceStatusEventListener;
import cn.full.cloud.module.oa.enums.BpmModelConstants;
import cn.full.cloud.module.oa.service.leave.OaLeaveApplyService;
import jakarta.annotation.Resource;
import cn.full.cloud.module.oa.enums.ApiConstants;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

/**
 * 请假申请审批结果监听器
 *
 * @author 芋道源码
 */
@RestController
@Validated
public class OaLeaveApplyStatusListener extends BpmProcessInstanceStatusEventListener {

    @Resource
    private OaLeaveApplyService leaveApplyService;

    @Override
    public String getProcessDefinitionKey() {
        return BpmModelConstants.LEAVE_APPLY;
    }

    @Override
    @PostMapping(ApiConstants.PREFIX + "/leave-apply/update-audit-status") // 提供给 bpm-server RPC 调用
    protected void onEvent(@RequestBody BpmProcessInstanceStatusEvent event) {
        leaveApplyService.updateLeaveApplyStatus(Long.valueOf(event.getBusinessKey()), event.getStatus());
    }

}
