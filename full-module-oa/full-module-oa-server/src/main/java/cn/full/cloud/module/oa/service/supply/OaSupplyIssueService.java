package cn.full.cloud.module.oa.service.supply;

import cn.full.cloud.framework.common.pojo.PageResult;
import cn.full.cloud.module.oa.controller.admin.supply.vo.issue.OaSupplyIssueReqVO;
import cn.full.cloud.module.oa.controller.admin.supply.vo.issue.OaSupplyIssuePageReqVO;
import cn.full.cloud.module.oa.controller.admin.supply.vo.issue.OaSupplyReturnReqVO;
import cn.full.cloud.module.oa.dal.dataobject.supply.OaSupplyApplyItemDO;

/**
 * 用品领用发放 Service 接口
 *
 * @author 芋道源码
 */
public interface OaSupplyIssueService {

    /**
     * 获得领用发放分页
     *
     * @param reqVO 请求参数
     * @return 领用发放分页
     */
    PageResult<OaSupplyApplyItemDO> getSupplyIssuePage(OaSupplyIssuePageReqVO reqVO);

    /**
     * 发放用品
     *
     * @param reqVO 请求参数
     * @param userId 操作人编号
     */
    void issueSupply(OaSupplyIssueReqVO reqVO, Long userId);

    /**
     * 确认归还用品
     *
     * @param reqVO 请求参数
     */
    void returnSupply(OaSupplyReturnReqVO reqVO);

}
